import logging
import os
import threading
import time
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import find_dotenv, load_dotenv
from pyrogram import Client, filters
from tinydb import Query, TinyDB

from app.config.cfg import API_HASH, API_ID, BOT_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

load_dotenv(find_dotenv())
db = TinyDB("app/database/db.json")
app = Client(
    "JADLOG_RASTREIO_BOT",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)


def rastrear_encomenda_jadlog(codigo_rastreio: str):
    logging.info(f"Tracking package with code: {codigo_rastreio}")
    url = f"https://www.jadlog.com.br/siteInstitucional/tracking_dev.jad?cte={codigo_rastreio}"
    headers = {
        "Accept": "text/html, *//*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Referer": "https://www.jadlog.com.br/siteInstitucional/tracking.jad",
    }

    try:
        logging.info("Sending GET request to Jadlog tracking endpoint")
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        logging.info("Received successful response from Jadlog tracking endpoint")

        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.find_all("tr", {"role": "row"})
        data = []
        for row in rows:
            cells = row.find_all("td", {"role": "gridcell"})
            if cells:
                data.append([cell.text.strip() for cell in cells])

        df = pd.DataFrame(
            data,
            columns=[
                "Data/Hora",
                "Ponto Origem",
                "Status",
                "Ponto Destino",
                "Documento",
            ],
        )
        logging.info(f"Parsed tracking data for package with code: {codigo_rastreio}")
        return df.to_dict("records")

    except requests.RequestException as e:
        logging.error(f"Error tracking package with code: {codigo_rastreio}: {e}")
        return None


def salvar_pacote(user_telegram_id: int, codigo_rastreio: str):
    logging.info(
        f"Saving package with code: {codigo_rastreio} for user {user_telegram_id}"
    )
    tracking_info = rastrear_encomenda_jadlog(codigo_rastreio)
    if tracking_info:
        db.insert(
            {
                "user_telegram_id": user_telegram_id,
                "codigo_rastreio": codigo_rastreio,
                "dados_rastreamento": tracking_info,
                "ultima_atualizacao": str(datetime.now()),
            }
        )
        app.send_message(user_telegram_id, "Dados salvos com sucesso!")
        logging.info(
            f"Package with code: {codigo_rastreio} saved for user {user_telegram_id}"
        )
    else:
        app.send_message(
            user_telegram_id,
            "Não foi possível obter os dados de rastreamento para salvar.",
        )
        logging.error(
            f"Failed to save package with code: {codigo_rastreio} for user {user_telegram_id}"
        )


def atualizar_pacotes():
    Pacote = Query()
    while True:
        for item in db:
            codigo_rastreio = item["codigo_rastreio"]
            logging.info(f"Updating package with code: {codigo_rastreio}")
            tracking_info_atualizado = rastrear_encomenda_jadlog(codigo_rastreio)
            if tracking_info_atualizado != item["dados_rastreamento"]:
                db.update(
                    {
                        "dados_rastreamento": tracking_info_atualizado,
                        "ultima_atualizacao": str(datetime.now()),
                    },
                    Pacote.codigo_rastreio == codigo_rastreio,
                )
                app.send_message(
                    item["user_telegram_id"], f"Encomenda {codigo_rastreio} atualizada."
                )
                logging.info(f"Package with code: {codigo_rastreio} updated")
            else:
                app.send_message(
                    item["user_telegram_id"],
                    f"Encomenda {codigo_rastreio} sem atualizações.",
                )
                logging.info(f"Package with code: {codigo_rastreio} has no updates")
        time.sleep(600)


@app.on_message(filters.command("atualizar"))
def atualizar_pacotes_usuario(client, message):
    user_telegram_id = message.from_user.id
    Pacote = Query()
    pacotes_usuario = db.search(Pacote.user_telegram_id == user_telegram_id)

    if not pacotes_usuario:
        message.reply_text("Você precisa cadastrar um pacote primeiro.")
        logging.info(f"No packages found for user {user_telegram_id}")
    else:
        for item in pacotes_usuario:
            codigo_rastreio = item["codigo_rastreio"]
            logging.info(
                f"Updating package for user {user_telegram_id} with code: {codigo_rastreio}"
            )
            tracking_info_atualizado = rastrear_encomenda_jadlog(codigo_rastreio)

            if tracking_info_atualizado != item["dados_rastreamento"]:
                db.update(
                    {
                        "dados_rastreamento": tracking_info_atualizado,
                        "ultima_atualizacao": str(datetime.now()),
                    },
                    (Pacote.codigo_rastreio == codigo_rastreio)
                    & (Pacote.user_telegram_id == user_telegram_id),
                )
                message.reply_text(f"Encomenda {codigo_rastreio} atualizada.")
                logging.info(
                    f"Package for user {user_telegram_id} with code: {codigo_rastreio} updated"
                )
            else:
                message.reply_text(f"Encomenda {codigo_rastreio} sem atualizações.")
                logging.info(
                    f"Package for user {user_telegram_id} with code: {codigo_rastreio} has no updates"
                )


def run_updater():
    logging.info("Starting package update thread")
    while True:
        atualizar_pacotes()


@app.on_message(filters.command("start"))
def start(client, message):
    logging.info(f"Received /start command from user {message.from_user.id}")
    message.reply_text(
        "Olá! Digite /rastrear <código de rastreio> para registrar seu pacote."
    )


@app.on_message(filters.command("rastrear"))
def rastrear(client, message):
    logging.info(f"Received /rastrear command from user {message.from_user.id}")
    codigo_rastreio = message.text.split(maxsplit=1)[1]
    salvar_pacote(message.from_user.id, codigo_rastreio)


if __name__ == "__main__":
    logging.info(f"APPLICATION START AT {datetime.now()}")
    app.run()
    updater_thread = threading.Thread(target=run_updater)
    updater_thread.start()
