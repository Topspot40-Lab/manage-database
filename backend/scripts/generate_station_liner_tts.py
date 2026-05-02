from __future__ import annotations

import os
import re
from pathlib import Path

import requests
from dotenv import load_dotenv


def safe_filename(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


def generate_tts_mp3(
    api_key: str,
    voice_id: str,
    text: str,
    output_path: Path,
    model_id: str = "eleven_multilingual_v2",
) -> None:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key,
    }

    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.75,
            "style": 0.20,
            "use_speaker_boost": True,
        },
    }

    response = requests.post(url, json=payload, headers=headers, timeout=120)

    if response.status_code != 200:
        raise RuntimeError(
            f"ElevenLabs API error {response.status_code}: {response.text}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)


def build_liner_lines_es() -> list[str]:
    return [
        "Estás escuchando TopSpot40, donde cada canción cuenta una historia.",
        "Esperamos que estés disfrutando este viaje musical con nosotros.",
        "Relájate y deja que los recuerdos sigan sonando en TopSpot40.",
        "La buena música nunca pasa de moda, y tú tampoco.",
        "Gracias por sintonizar TopSpot40, tu banda sonora a través del tiempo.",
        "Quédate aquí, vienen más clásicos en camino.",
        "Ya estás en el ritmo, sigue con nosotros.",
        "Los éxitos siguen llegando aquí en TopSpot40.",
        "Música que te mueve, solo en TopSpot40.",
        "Deja que el ritmo te lleve un poco más lejos.",
        "De una gran canción a la siguiente, esto es TopSpot40.",
        "Llevándote al pasado, una canción a la vez.",
        "La banda sonora de tu vida continúa aquí.",
        "Mantente en sintonía, vienen más favoritas.",
        "Trayendo de vuelta la magia de la música.",
        "Estás justo donde vive la música.",
        "Canciones eternas, recuerdos sin fin.",
        "No le cambies, sigue en TopSpot40.",
        "Siente la vibra, siente la música.",
        "Un poco de nostalgia llega muy lejos.",
        "Estás viajando por los clásicos con TopSpot40.",
        "Cada canción tiene un recuerdo. ¿Cuál es el tuyo?",
        "Que sigan los buenos tiempos.",
        "Música que resiste el paso del tiempo.",
        "Más éxitos, más recuerdos, más TopSpot40.",
        "El viaje continúa, quédate con nosotros.",
        "Apenas estamos calentando motores, viene mucho más.",
        "Tu máquina personal del tiempo, TopSpot40.",
        "Donde el pasado suena mejor que nunca.",
        "Gracias por escuchar. Tenemos más música en camino.",
    ]


def build_liner_lines_ptbr() -> list[str]:
    return [
        "Você está ouvindo TopSpot40, onde cada música conta uma história.",
        "Esperamos que você esteja curtindo essa viagem musical com a gente.",
        "Relaxe e deixe as lembranças continuarem tocando no TopSpot40.",
        "Música boa nunca sai de moda, e você também não.",
        "Obrigado por sintonizar o TopSpot40, sua trilha sonora através do tempo.",
        "Fique por aqui, vem mais clássicos pela frente.",
        "Você já entrou no clima, continue com a gente.",
        "Os sucessos não param por aqui no TopSpot40.",
        "Música que emociona você, só no TopSpot40.",
        "Deixe o ritmo levar você um pouco mais longe.",
        "De uma grande faixa para outra, TopSpot40.",
        "Levando você de volta, uma música de cada vez.",
        "A trilha sonora da sua vida continua aqui.",
        "Continue ligado, vem mais favoritas por aí.",
        "Trazendo de volta a magia da música.",
        "Você está exatamente onde a música vive.",
        "Canções atemporais, memórias sem fim.",
        "Não mude de estação, fique no TopSpot40.",
        "Sinta a vibe, sinta a música.",
        "Um pouco de nostalgia vai longe.",
        "Você está passeando pelos clássicos com TopSpot40.",
        "Cada música tem uma lembrança. Qual é a sua?",
        "Que os bons tempos continuem.",
        "Música que resiste ao tempo.",
        "Mais sucessos, mais lembranças, mais TopSpot40.",
        "A viagem continua, fique com a gente.",
        "Estamos só começando, ainda vem muito mais.",
        "Sua máquina do tempo pessoal, TopSpot40.",
        "Onde o passado soa melhor do que nunca.",
        "Obrigado por ouvir. Temos mais música a caminho.",
    ]


def main() -> None:
    load_dotenv()

    api_key = os.getenv("ELEVENLABS_API_KEY")

    jobs = [
        {
            "language": "es",
            "voice_id": os.getenv("VOICE_ID_ARTIST_ES") or os.getenv("VOICE_ID_ARTIST"),
            "output_dir": Path("data/mp3_files/station_liners/es"),
            "lines": build_liner_lines_es(),
        },
        {
            "language": "ptbr",
            "voice_id": os.getenv("VOICE_ID_ARTIST_PTBR") or os.getenv("VOICE_ID_ARTIST"),
            "output_dir": Path("data/mp3_files/station_liners/ptbr"),
            "lines": build_liner_lines_ptbr(),
        },
    ]

    if not api_key:
        raise RuntimeError("Missing ELEVENLABS_API_KEY in .env")

    for job in jobs:
        language = job["language"]
        voice_id = job["voice_id"]
        output_dir = job["output_dir"]
        lines = job["lines"]

        if not voice_id:
            raise RuntimeError(f"Missing voice ID for language: {language}")

        print(f"\n🎙️ Generating {language} station liners into: {output_dir.resolve()}")

        for index, line in enumerate(lines, start=1):
            filename = f"liner_{index:02}.mp3"
            output_path = output_dir / filename

            if output_path.exists():
                print(f"Skipping existing file: {filename}")
                continue

            print(f"[{index:02}/{len(lines):02}] Creating {filename}")
            generate_tts_mp3(
                api_key=api_key,
                voice_id=voice_id,
                text=line,
                output_path=output_path,
            )

    print("\n✅ Done. ES and PTBR station liner MP3 files created.")


if __name__ == "__main__":
    main()