"""A harmless window for trying omni-all safely.

Run it, then start omni-all with OMNI_CONFINE_TITLE="omni-all sandbox" so
the agent can only click/type inside this window. Everything it does is
logged to stdout.

Example tasks: "clique no botão Somar 3 vezes e me diga o total",
"escreva 'olá mundo' no campo de nota e clique em Salvar".
"""
import tkinter as tk

root = tk.Tk()
root.title("omni-all sandbox")
root.geometry("520x360+120+120")
root.attributes("-topmost", True)

total = tk.IntVar(value=0)
saved = tk.StringVar(value="Nada salvo ainda")

tk.Label(root, text="Área de teste do omni-all", font=("Segoe UI", 16, "bold")).pack(pady=12)

row = tk.Frame(root)
row.pack(pady=6)
tk.Label(row, text="Total:", font=("Segoe UI", 13)).pack(side="left")
tk.Label(row, textvariable=total, font=("Segoe UI", 13, "bold")).pack(side="left", padx=6)


def add():
    total.set(total.get() + 1)
    print("Somar ->", total.get(), flush=True)


tk.Button(root, text="Somar", font=("Segoe UI", 12), width=12, command=add).pack(pady=6)

tk.Label(root, text="Nota:", font=("Segoe UI", 12)).pack()
note = tk.Entry(root, font=("Segoe UI", 12), width=32)
note.pack(pady=4)


def save():
    saved.set(f"Salvo: {note.get()}")
    print("Salvar ->", note.get(), flush=True)


tk.Button(root, text="Salvar", font=("Segoe UI", 12), width=12, command=save).pack(pady=6)
tk.Label(root, textvariable=saved, font=("Segoe UI", 12)).pack(pady=6)

root.mainloop()
