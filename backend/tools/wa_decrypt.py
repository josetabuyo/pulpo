"""
Descarga y descifra audio PTT de WhatsApp Web.
Uso: python wa_decrypt.py
"""
import asyncio
import base64
import httpx
import os
import sys
import tempfile
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def derive_media_key(media_key_b64: str, media_type: str = "audio") -> bytes:
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes

    type_info = {
        "image": b"WhatsApp Image Keys",
        "video": b"WhatsApp Video Keys",
        "audio": b"WhatsApp Audio Keys",
        "ptt": b"WhatsApp Audio Keys",
        "document": b"WhatsApp Document Keys",
    }
    info = type_info.get(media_type, b"WhatsApp Audio Keys")
    media_key = base64.b64decode(media_key_b64)

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=112,
        salt=None,
        info=info,
    )
    return hkdf.derive(media_key)


def decrypt_wa_enc(enc_bytes: bytes, media_key_b64: str, media_type: str = "ptt") -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    expanded = derive_media_key(media_key_b64, media_type)
    iv = expanded[:16]
    cipher_key = expanded[16:48]
    # mac_key = expanded[48:80]  # skip MAC validation for speed

    # enc file: last 10 bytes = MAC, rest = ciphertext
    ciphertext = enc_bytes[:-10]

    cipher = Cipher(algorithms.AES(cipher_key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(ciphertext) + decryptor.finalize()
    return decrypted


async def download_and_decrypt(direct_path: str, media_key_b64: str, output_path: str) -> str:
    """Descarga el .enc, lo descifra y guarda como .ogg. Retorna la ruta del archivo."""
    cdn_url = "https://mmg.whatsapp.net" + direct_path

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(cdn_url, headers={
            "User-Agent": "WhatsApp/2.23.20.0 A",
            "Origin": "https://web.whatsapp.com",
            "Referer": "https://web.whatsapp.com/",
        })
        resp.raise_for_status()
        enc_bytes = resp.content

    decrypted = decrypt_wa_enc(enc_bytes, media_key_b64)

    with open(output_path, "wb") as f:
        f.write(decrypted)

    return output_path


# Datos de los PTTs del grupo "Desarrollo SIGIRH 2025" de la_piquiteria
PTT_MESSAGES = [
    {
        "id": "ACFCE45FEBAB550517B69AEE779B0034",
        "t": 1773758502,
        "timestamp": "2026-03-17 11:41",
        "duration": 236,
        "mediaKey": "Uuj9x95wvTh/Dj0ODsBpkeIF6GeJtyK4IMOdSxGpsD4=",
        "directPath": "/v/t62.7117-24/559976643_1804424410235449_888141480104688388_n.enc?ccb=11-4&oh=01_Q5Aa4AHJtt3bo88Mn-SY_D5yrZGRkUgjkPou48TpaRw7W_c22A&oe=69E0EB63&_nc_sid=5e03e0",
    },
    {
        "id": "ACF4A0EE67B870AC3877E7610AAECCB0",
        "t": 1773782570,
        "timestamp": "2026-03-17 18:22",
        "duration": 62,
        "mediaKey": "hGmfP2hdDUjeCDwsxutjS7V5zCwvjcZg/x7uy8AEkOc=",
        "directPath": "/v/t62.7117-24/559550555_802079915754419_1813407635611286015_n.enc?ccb=11-4&oh=01_Q5Aa4AGW2IrmM9E5OqjIHyX3AOswMmvjJI5TWEDR6HCvIRl_UA&oe=69E1330A&_nc_sid=5e03e0",
    },
    {
        "id": "3A7E78F5488826368D6F",
        "t": 1773782686,
        "timestamp": "2026-03-17 18:24",
        "duration": 38,
        "mediaKey": "o+CcBWSMZZuDoQC7nR1LLKoSn3rIssKA+OMUPMVBX/w=",
        "directPath": "/v/t62.7117-24/606644336_830307150107259_19300339672838288_n.enc?ccb=11-4&oh=01_Q5Aa4AFpYi8c9Tm7ksaDzZMVIAeENNILp3GF458Wi_GiDv-fdA&oe=69E1395D&_nc_sid=5e03e0",
    },
    {
        "id": "AC285147B2237282F96A61CEE807011E",
        "t": 1773782800,
        "timestamp": "2026-03-17 18:26",
        "duration": 5,
        "mediaKey": "kYNpN9AtO2K1tpXsyBdgrKKJgh3Iys054lvjRiu20sU=",
        "directPath": "/v/t62.7117-24/552225487_1238827248395943_758291158568313505_n.enc?ccb=11-4&oh=01_Q5Aa4AGc4-LC7pbaT1zomkUBQ99A6OFxWObwZNTwTVM0hnbKQw&oe=69E1308A&_nc_sid=5e03e0",
    },
]


async def main():
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")

    from tools.transcription import transcribe
    from tools.summarizer import accumulate, clear_contact
    from datetime import datetime

    empresa_id = "la_piquiteria"
    contact_phone = "Desarrollo SIGIRH\xa0\xa02025"

    print(f"Procesando {len(PTT_MESSAGES)} audios PTT...\n")

    for ptt in PTT_MESSAGES:
        ts_str = ptt["timestamp"]
        print(f"[{ts_str}] Descargando audio ({ptt['duration']}s)...")

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            await download_and_decrypt(ptt["directPath"], ptt["mediaKey"], tmp_path)
            print(f"  → Descifrado OK ({Path(tmp_path).stat().st_size} bytes)")

            print(f"  → Transcribiendo...")
            text = await transcribe(tmp_path)
            print(f"  → Transcripción: {text[:120]}")

            # Parsear timestamp para acumular
            ts_dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M")

            # Acumular en el summarizer (reemplazará el placeholder existente)
            accumulate(
                empresa_id=empresa_id,
                contact_phone=contact_phone,
                contact_name=contact_phone,
                msg_type="audio",
                content=f"Fabian Miranda: {text}",
                timestamp=ts_dt,
            )
            print(f"  → Acumulado en summarizer ✓\n")

        except Exception as e:
            print(f"  ✗ Error: {e}\n")
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
