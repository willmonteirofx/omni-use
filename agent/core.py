"""The computer-use loop: screenshot -> OmniParser V2 -> Qwen picks the next
action -> OpenJev-style decide() gates it -> SendInput executes it.

decide() (one forward pass reading the options' logits, no generation) is
used twice: to hold back actions that look destructive until the user
confirms them, and to check a claimed "done" against what is on screen.
"""
import datetime
import json
import threading
import time

import config
import control
import vision
from llm_client import LLMClient

SYSTEM = """Você controla o computador Windows do usuário, por mouse e teclado,
para cumprir uma tarefa. A cada passo você vê a tela (screenshot com as caixas
numeradas do OmniParser, quando disponível) e a lista dos elementos detectados:
[id] tipo "conteúdo" @(x,y) LxA (centro e tamanho).
Responda SOMENTE um JSON com o próximo passo:
{"thought": "<curto, em português>", "action": "<ação>", ...}

Ações:
- {"action":"click","id":N}  (também "double_click", "right_click")
- {"action":"type","text":"..."}  digita no elemento que está com o foco
- {"action":"key","keys":"enter"}  tecla ou atalho ("ctrl+l", "esc", "win", "alt+tab"...)
- {"action":"scroll","direction":"down","id":N}  id opcional (onde rolar)
- {"action":"wait"}  a tela ainda está carregando
- {"action":"done","answer":"<resposta final ao usuário, em português>"}

Princípios:
- Um passo por vez, e só com certeza. Os ids mudam a cada tela: use apenas ids
  da lista atual. Antes de agir, confira na imagem e na lista que o alvo é
  exatamente o que a tarefa precisa.
- Observe o resultado de cada passo no histórico; se algo não funcionou, não
  repita igual: mude de abordagem.
- Não mexa no que o usuário está fazendo além do necessário para a tarefa.
- Nunca apague, feche sem salvar, compre, envie ou pague nada que a tarefa não
  peça explicitamente.
- Quando a tarefa pedir uma informação, termine com done e a informação lida
  da tela atual (não suponha valores)."""

FOCUS_KEYS = ("ctrl+l", "ctrl+f", "ctrl+k", "ctrl+e", "/", "f6", "alt+d")

RISK_QUESTION = ("Esta ação pode causar perda de dados ou efeito irreversível que a tarefa "
                 "NÃO pediu explicitamente (apagar, fechar sem salvar, enviar, comprar, pagar, "
                 "desinstalar, sobrescrever)?")


def _last_json(text):
    """The last {...} object in a reply (the model may write around it)."""
    end = text.rfind("}")
    while end != -1:
        start = text.rfind("{", 0, end)
        while start != -1:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                start = text.rfind("{", 0, start)
        end = text.rfind("}", 0, end)
    return None


class Stopped(Exception):
    pass


class Run:
    """One task. Runs on its own thread; the HTTP server reads `status()`
    and calls pause/resume/stop."""

    def __init__(self, task, llm: LLMClient):
        self.task = task
        self.llm = llm
        self.state = "running"  # running | paused | confirm | done | failed | stopped
        self.pause_reason = ""
        self.message = "Lendo a tela..."
        self.answer = ""
        self.log = []  # [{step, thought, action}]
        self.clicks = 0  # bumps on every click, the shell animates a ripple
        self.timings = {}
        self.plan = ""
        self.debug_seq = 0  # bumps when debug_info (GET /debug) changes
        self.debug_info = {}
        self._resume = threading.Event()
        self._resume.set()
        self._pause_count = 0
        self._approved = None  # action the user allowed after a "confirm"
        # Typing is only allowed right after something that surely focused a
        # field: a click that changed the screen, a focus shortcut, or typing.
        self._focus_ok = False
        # Attempts that were refused or changed nothing: "<action> <target>".
        self._failed = []
        self._log_file = config.LOG_DIR / time.strftime("run-%Y%m%d-%H%M%S.jsonl")
        self._lock = threading.Lock()
        self.thread = threading.Thread(target=self._main, daemon=True)
        self.thread.start()

    # --- control from the server/shell ---------------------------------

    def pause(self, reason="user"):
        with self._lock:
            if self.state == "running":
                self.state = "paused"
                self.pause_reason = reason
                self._pause_count += 1
                self._resume.clear()

    def resume(self):
        with self._lock:
            if self.state in ("paused", "confirm"):
                self.state = "running"
                self.pause_reason = ""
                self._resume.set()

    def stop(self):
        with self._lock:
            if self.state in ("running", "paused", "confirm"):
                self.state = "stopped"
                self.message = "Parado."
                self._resume.set()

    def status(self):
        return {
            "task": self.task, "state": self.state, "pause_reason": self.pause_reason,
            "message": self.message, "answer": self.answer, "steps": len(self.log),
            "log": self.log[-12:], "clicks": self.clicks, "timings": self.timings,
            "debug_seq": self.debug_seq,
        }

    # --- loop ------------------------------------------------------------

    def _halted(self):
        return self.state != "running"

    def _checkpoint(self):
        """Blocks while paused. Returns True when the step must start over
        (a pause happened, the screen may have changed); raises when stopped."""
        paused_before = self._pause_count
        self._resume.wait()
        if self.state == "stopped":
            raise Stopped()
        return self._pause_count != paused_before

    def _main(self):
        try:
            vision.load()
            history = []
            rejected_done = 0
            self.message = "Planejando..."
            self.plan = self._make_plan(vision.screenshot())
            for step in range(1, config.MAX_STEPS + 1):
                while True:
                    count = self._pause_count
                    self._checkpoint()
                    shot = vision.screenshot()
                    elements, labeled, parse_s = vision.parse(shot)
                    listing = self._listing(elements)
                    t0 = time.perf_counter()
                    action = self._ask(listing, history, shot.size, labeled)
                    self.timings = {"parse_s": round(parse_s, 2),
                                    "llm_s": round(time.perf_counter() - t0, 2),
                                    "elements": len(elements)}
                    self._checkpoint()
                    if self._pause_count == count:
                        break  # no pause while we were looking/thinking
                self._debug_frame(elements, action, step)
                self.message = action.get("thought") or action.get("action", "")
                entry = {"step": step, "thought": self.message,
                         "action": {k: v for k, v in action.items() if k != "thought"}}
                self.log.append(entry)
                self._write_log(entry)

                if action.get("action") == "done":
                    verdict = self.llm.decide(
                        "A tela atual mostra evidência clara de que a tarefa foi concluída "
                        "(por exemplo o texto digitado ou o valor esperado visível)?",
                        [("sim", "concluída"), ("nao", "ainda falta algo")],
                        {"tarefa": self.task, "tela": listing[:6000],
                         "historico": history[-8:], "resposta": action.get("answer", "")})
                    if verdict.get("nao", 0) > 0.4 and rejected_done < 2:
                        rejected_done += 1
                        history.append({"acao": "done", "resultado":
                                        "a verificação diz que a tarefa ainda NÃO foi concluída; continue"})
                        continue
                    self.answer = action.get("answer") or "Concluído."
                    self.state, self.message = "done", self.answer
                    return

                result = self._execute(action, elements, shot)
                kind = action.get("action")
                self._focus_ok = (
                    (kind == "click" and result.startswith("cliquei"))
                    or (kind == "key" and action.get("keys", "").lower() in FOCUS_KEYS and result.startswith("pressionei"))
                    or (kind == "type" and result.startswith("digitei") and self._focus_ok))
                # No ids in the history: they change every screenshot and the
                # model would reuse stale ones. The result names the target.
                history.append({"acao": action.get("action"), "resultado": result,
                                **({"texto": action.get("text", "")} if action.get("action") == "type" else {})})
                entry["result"] = result
                self._write_log({"step": step, "result": result})
                time.sleep(0.6)  # let the UI react before the next screenshot
            self.state, self.message = "failed", f"Parei após {config.MAX_STEPS} passos sem concluir."
        except Stopped:
            pass
        except Exception as e:  # never leave the UI waiting without an answer
            self.state, self.message = "failed", f"Erro: {e}"
            self._write_log({"error": repr(e)})

    def _debug_frame(self, elements, action, step):
        """OmniParser's boxes (screen pixels) + the chosen target, drawn by the
        shell's debug overlay right over the real screen."""
        self.debug_info = {
            "step": step, "target": action.get("id"),
            "action": action.get("action"),
            "boxes": [{"id": e["id"], "box": e["box"], "type": e["type"], "content": e["content"][:40]}
                      for e in elements],
        }
        self.debug_seq += 1

    def _write_log(self, record):
        try:
            self._log_file.parent.mkdir(exist_ok=True)
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _make_plan(self, shot):
        """Imagines, before touching anything, the UI steps the task needs."""
        elements, labeled, _ = vision.parse(shot)
        msg, _ = self.llm.chat([
            {"role": "system", "content": "Você planeja o uso de um computador Windows por mouse e "
             "teclado, olhando a tela. Escreva em português uma lista numerada curta (3 a 8 itens) "
             "com os passos concretos de interface para cumprir a tarefa, a partir da tela atual: "
             "o que abrir, onde clicar, o que digitar e como saber que cada passo deu certo. "
             "A tela atual pode não ter nada a ver com a tarefa: não use o que o usuário "
             "estava fazendo se a tarefa não pede."},
            {"role": "user", "content": self.llm.user_content(
                f"Tarefa: {self.task}\nJanela em primeiro plano: \"{control.foreground_title()}\"\n\n"
                f"Tela atual:\n{self._listing(elements)[:8000]}", vision.for_model(labeled))},
        ], max_tokens=4096, thinking=True)
        plan = (msg.get("content") or "").strip()
        self._write_log({"task": self.task, "plan": plan})
        return plan

    def _listing(self, elements):
        lines = []
        for e in elements:
            content = e["content"].replace("\n", " ")[:80]
            x1, y1, x2, y2 = e["box"]
            lines.append(f'[{e["id"]}] {e["type"]} "{content}" @{e["center"]} {x2 - x1}x{y2 - y1}')
        return "\n".join(lines)

    def _ask(self, listing, history, size, labeled):
        user = (f"Data: {datetime.date.today().isoformat()}\nTarefa: {self.task}\n"
                f"Plano (imaginado antes de começar):\n{self.plan}\n"
                f"Diga no thought em qual passo do plano você está.\n"
                f"Tela {size[0]}x{size[1]}, janela em primeiro plano: \"{control.foreground_title()}\"\n\n"
                f"Elementos:\n{listing}\n\n"
                f"Passos anteriores (mais recente por último):\n"
                f"{json.dumps(history[-10:], ensure_ascii=False) if history else 'nenhum'}")
        msg, _ = self.llm.chat([{"role": "system", "content": SYSTEM},
                                {"role": "user", "content": self.llm.user_content(user, vision.for_model(labeled))}],
                               max_tokens=4096, thinking=True)
        self._write_log({"reasoning": (msg.get("reasoning_content") or "")[-1500:]})
        action = _last_json(msg.get("content") or "")
        if action is None:
            return {"action": "wait", "thought": "resposta inválida do modelo"}
        # Small models sometimes nest it: {"action": {"action": "click", "id": 3}}
        while isinstance(action.get("action"), dict):
            action = {**action, **action["action"]}
        return action

    # --- execution ---------------------------------------------------------

    def _execute(self, action, elements, shot):
        kind = action.get("action")
        by_id = {e["id"]: e for e in elements}
        target = by_id.get(action.get("id")) if action.get("id") is not None else None

        if kind in ("click", "double_click", "right_click") and target is None:
            return f"id {action.get('id')} não existe na tela atual"
        if kind == "wait":
            time.sleep(1.5)
            return "esperei"
        if kind not in ("click", "double_click", "right_click", "type", "key", "scroll"):
            return f"ação desconhecida: {kind}"

        refusal = self._confine_check(action, target)
        if refusal:
            return refusal

        if kind == "type" and not self._focus_ok:
            return ("NÃO digitei: não há campo focado com certeza. Clique no campo de texto "
                    "(ou ctrl+l para a barra de endereço) e só então digite.")
        if kind in ("click", "double_click", "right_click", "type", "key") and not self._risk_ok(action, target):
            return "o usuário não autorizou esta ação"

        attempt = f'{kind} "{target["content"][:50]}"' if target is not None else None
        if attempt in self._failed:
            return (f"NÃO executei: {attempt} já falhou antes. Proponha algo diferente "
                    "(outro elemento, teclado, rolar, esperar).")
        if target is not None:
            doubt = self._certain(action, target, elements, shot)
            if doubt:
                self._failed.append(attempt)
                return doubt
        try:
            if target is not None:
                control.glide(*target["center"], should_stop=self._halted)
            if kind in ("click", "double_click", "right_click"):
                before = vision.screenshot()
                with _shell_out_of_the_way(*target["center"]):
                    control.click("right" if kind == "right_click" else "left", double=kind == "double_click")
                self.clicks += 1
                time.sleep(0.4)
                what = f'cliquei em "{target["content"][:40]}" @{target["center"]}'
                region = control.window_rect_at(*target["center"])
                if not vision.changed(before.crop(region), vision.screenshot().crop(region)):
                    self._failed.append(attempt)
                    return what + (" — a tela NÃO mudou nada. Não clique de novo nesse elemento; "
                                   "escolha outro.")
                return what
            if kind == "type":
                text = action.get("text", "")
                region = control.window_rect(control.user32.GetForegroundWindow())
                before = vision.screenshot().crop(region)
                control.type_text(text)
                time.sleep(0.3)
                return f'digitei "{text[:60]}" — ' + self._typed_where(before, vision.screenshot().crop(region), text)
            if kind == "key":
                control.press(action.get("keys", ""))
                return f'pressionei {action.get("keys")}'
            control.scroll(action.get("direction", "down"))
            return f'rolei para {action.get("direction", "down")}'
        except control.Cancelled:
            return "interrompido pelo usuário"
        except ValueError as e:
            return str(e)

    @staticmethod
    def _typed_where(before, after, text):
        """Where did the keystrokes land? OCR of the region that changed
        between the screenshots taken right before and after typing."""
        seen = vision.changed_text(before, after)
        if seen is None:
            return "mas NADA mudou na tela: nenhum campo estava focado. Clique na caixa de entrada e digite de novo."
        words = [w for w in text.lower().split() if len(w) > 2]
        if not words or any(w in seen.lower() for w in words):
            return f'confirmado: o texto apareceu na tela ("{seen[:60]}"). Não digite de novo.'
        return f'a tela mudou, mas lá aparece "{seen[:60]}"; confira se foi no campo certo.'

    def _certain(self, action, target, elements, shot):
        """The mouse only moves when decide() is sure (p >= CERTAINTY) that this
        element is exactly the one the current step needs. Returns None when
        sure, otherwise the reason (fed back to the model)."""
        cx, cy = target["center"]
        near = [f'"{e["content"][:40]}" @{e["center"]}' for e in elements
                if e is not target and abs(e["center"][0] - cx) < 200 and abs(e["center"][1] - cy) < 120][:12]
        x1, y1, x2, y2 = target["box"]
        probs = self.llm.decide(
            "O elemento alvo é EXATAMENTE o que deve receber esta ação agora, para avançar a "
            "tarefa conforme o plano? Responda sim só com certeza absoluta.",
            [("sim", "certeza absoluta"), ("nao", "não tenho certeza ou é outro elemento")],
            {"tarefa": self.task, "plano": self.plan, "intencao": action.get("thought", ""),
             "acao": action.get("action"),
             "alvo": {"tipo": target["type"], "conteudo": target["content"], "centro": target["center"],
                      "tamanho": f"{x2 - x1}x{y2 - y1}"},
             "vizinhos": near, "janela_em_primeiro_plano": control.foreground_title()},
            image=vision.around(shot, target["box"]))
        p = probs.get("sim", 0.0)
        self._write_log({"certainty": round(p, 2), "target": target["content"][:60]})
        self.debug_info = {**self.debug_info, "certainty": round(p, 2)}
        if p >= config.CERTAINTY:
            return None
        return (f'NÃO movi o mouse: certeza de só {p:.0%} de que "{target["content"][:40]}" é o alvo certo. '
                "Olhe a lista de novo e escolha um elemento que seja inequivocamente o certo, ou mude de abordagem.")

    def _risk_ok(self, action, target):
        """decide() whether the action looks destructive; if so, hold it
        until the user resumes (approves) or stops."""
        key = json.dumps(action, sort_keys=True, ensure_ascii=False)
        if self._approved == key:
            return True
        probs = self.llm.decide(RISK_QUESTION, [("nao", "ação segura"), ("sim", "arriscada")],
                                {"tarefa": self.task, "acao": action,
                                 "alvo": target["content"] if target else control.foreground_title()})
        if probs.get("sim", 0) < 0.5:
            return True
        with self._lock:
            if self.state != "running":
                return False
            self.state = "confirm"
            self.pause_reason = f"Confirmar: {action.get('thought') or action.get('action')}"
            self._resume.clear()
        self._resume.wait()
        if self.state == "stopped":
            raise Stopped()
        self._approved = key
        return True

    def _confine_check(self, action, target):
        kind = action.get("action")
        if not config.CONFINE_TITLE:
            return None
        hwnd = control.find_window(config.CONFINE_TITLE)
        if not hwnd:
            return f"janela de teste '{config.CONFINE_TITLE}' não encontrada; ação recusada"
        if target is not None and not control.point_in(control.window_rect(hwnd), *target["center"]):
            return "alvo fora da janela de teste; ação recusada"
        if kind in ("type", "key") and config.CONFINE_TITLE.lower() not in control.foreground_title().lower():
            return "a janela de teste não está em primeiro plano; digitação recusada"
        if kind == "key" and any(k in action.get("keys", "").lower() for k in ("win", "alt")):
            return "atalho de sistema recusado no modo de teste"
        return None


class _shell_out_of_the_way:
    """Hides the floating input while clicking a point it covers, so the
    click reaches the app underneath."""

    def __init__(self, x, y):
        self.hwnd = control.find_window(config.SHELL_TITLE, exact=True)
        self.hide = bool(self.hwnd) and control.point_in(control.window_rect(self.hwnd), x, y)

    def __enter__(self):
        if self.hide:
            control.user32.ShowWindow(self.hwnd, 0)  # SW_HIDE
            time.sleep(0.05)

    def __exit__(self, *exc):
        if self.hide:
            control.user32.ShowWindow(self.hwnd, 4)  # SW_SHOWNOACTIVATE
