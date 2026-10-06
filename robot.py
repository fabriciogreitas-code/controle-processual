import json, os, smtplib, requests
from datetime import datetime, timezone
from email.mime.text import MIMEText

BASE = "https://api-publica.datajud.cnj.jus.br/api_publica_{alias}/"
ALIASES = {
    "TJRJ": "tjrj", "TRT1": "trt1", "TRT2": "trt2",
    "TRF2/JFRJ": "trf2", "TRF2": "trf2", "STJ": "stj", "STF": "stf",
}

def alias(tribunal):
    return ALIASES.get(tribunal.strip().upper())

def consultar(cnj, trib):
    a = alias(trib)
    if not a:
        return []
    url = BASE.format(alias=a)
    r = requests.post(url, headers={"APIKey": os.environ["DATAJUD_APIKEY"]},
                      json={"query": {"match": {"numeroProcesso": cnj}}}, timeout=60)
    r.raise_for_status()
    hits = r.json().get("hits", {}).get("hits", [])
    for h in hits:
        src = h.get("_source", {})
        if src.get("numeroProcesso") == cnj:
            movs = []
            for m in src.get("movimentos", []):
                data = (m.get("dataHora") or "")[:10]
                nome = (m.get("nome") or "").strip()
                if data and nome:
                    movs.append({"data": data, "descricao": nome})
            movs.sort(key=lambda x: x["data"])
            return movs
    return []

def main():
    with open("processos_rob.json", encoding="utf-8") as f:
        processos = json.load(f)
    estado = {}
    if os.path.exists("estado.json"):
        with open("estado.json", encoding="utf-8") as f:
            estado = json.load(f)

    novidades = []
    for p in processos:
        cnj = p["numeroCNJ"]
        movs = consultar(cnj, p.get("tribunal", ""))
        vistos = set(estado.get(cnj, []))
        for m in movs:
            chave = m["data"] + "|" + m["descricao"].lower()
            if chave not in vistos:
                novidades.append({"numeroCNJ": cnj, "tribunal": p.get("tribunal", ""),
                                  "cliente": p.get("cliente", ""), **m})
                vistos.add(chave)
        estado[cnj] = sorted(vistos)

    saida = {"geradoEm": datetime.now(timezone.utc).isoformat(), "novidades": novidades}
    with open("movimentacoes.json", "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    with open("estado.json", "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)

    if novidades and os.environ.get("SMTP_USER"):
        linhas = "".join(
            f"<li>{n['data']} — {n['numeroCNJ']} ({n['cliente']}): {n['descricao']}</li>"
            for n in novidades)
        msg = MIMEText(f"<h3>Movimentações novas ({len(novidades)})</h3><ul>{linhas}</ul>"
                       "<p>Fabrício Freitas Advocacia — Robô DataJud</p>", "html")
        msg["Subject"] = f"Controle Processual: {len(novidades)} movimentação(ões) nova(s)"
        msg["From"] = os.environ["SMTP_USER"]
        msg["To"] = os.environ.get("EMAIL_DESTINO", os.environ["SMTP_USER"])
        s = smtplib.SMTP("smtp.gmail.com", 587)
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)
        s.quit()

    print(f"OK: {len(novidades)} novidade(s) em {len(processos)} processo(s).")

if __name__ == "__main__":
    main()