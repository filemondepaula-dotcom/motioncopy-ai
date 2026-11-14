import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))

app = FastAPI(title="MotionCopy AI API", version="0.2.0")

# Durante o desenvolvimento, permite testar a interface local.
# Em produção, substitua "*" pelo domínio real do aplicativo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

VIDEO_MIMES = {
    "video/mp4", "video/quicktime", "video/webm", "video/x-msvideo",
    "video/mpeg", "video/x-flv", "video/x-ms-wmv", "video/3gpp",
}

ANALYSIS_INSTRUCTIONS = """
Você é o motor de análise de movimentos do MotionCopy AI.
Analise o VÍDEO apenas como referência de MOVIMENTO. Não transfira cenário,
roupas, identidade, aparência, objetos, iluminação ou fundo para a imagem final.

Observe a sequência temporal e descreva apenas o que for visualmente verificável:
- ações corporais e sua ordem;
- postura, direção e deslocamento do corpo;
- gestos das mãos e braços;
- movimentos da cabeça e expressões faciais observáveis;
- poses e transições;
- movimento de câmera, separado dos movimentos da pessoa;
- tempos aproximados de início e fim.

Não invente movimentos, detalhes ou tempos. Se algo não estiver claro, indique
"incerto". Diferencie movimento da pessoa de movimento da câmera. Não descreva
o cenário, roupas ou aparência do vídeo, exceto para dizer que devem ser ignorados.

Responda SOMENTE em JSON válido, neste formato:
{
  "duration_seconds": 0,
  "summary": "Resumo breve, somente dos movimentos.",
  "timeline": [
    {
      "start_seconds": 0,
      "end_seconds": 3,
      "body_movement": "Ação corporal observável",
      "hands_and_arms": "Gestos observáveis ou não identificados",
      "head_and_expression": "Movimento da cabeça/expressão ou não identificados",
      "camera_movement": "Movimento da câmera ou câmera estável",
      "confidence": "alta, média ou baixa"
    }
  ],
  "uncertainties": ["Pontos que não puderam ser determinados"]
}
"""

def extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("A IA não retornou JSON válido.")
    return json.loads(text[start:end + 1])

def make_prompts(result: dict[str, Any]) -> dict[str, str]:
    timeline = result.get("timeline", [])
    sequence = []
    for item in timeline:
        start = item.get("start_seconds", "?")
        end = item.get("end_seconds", "?")
        sequence.append(
            f'{start}s–{end}s: {item.get("body_movement", "")}; '
            f'mãos/braços: {item.get("hands_and_arms", "")}; '
            f'cabeça/expressão: {item.get("head_and_expression", "")}; '
            f'câmera: {item.get("camera_movement", "")}.'
        )
    movements = "\n".join(sequence) or result.get("summary", "")

    fixed_rules = (
        "Use a imagem original fornecida na plataforma de geração como ÚNICA "
        "referência de aparência e cenário. Preserve a identidade, rosto, cabelo, "
        "corpo, roupas, acessórios, objetos, fundo, ambiente, iluminação, cores, "
        "enquadramento e composição da imagem original. O vídeo de referência "
        "serve exclusivamente para extrair movimentos. Não copie dele cenário, "
        "fundo, roupas, objetos, iluminação, aparência ou identidade. "
        "Não invente ações. Mantenha anatomia e continuidade naturais. "
        "Não adicione texto, legendas, logotipos ou elementos extras."
    )

    short = (
        "Reproduza somente os movimentos principais do vídeo de referência, "
        "mantendo a ordem das ações e transições naturais. "
        + (result.get("summary") or "")
        + "\n\n" + fixed_rules
    )
    detailed = (
        "Reproduza fielmente a sequência cronológica de movimentos descrita abaixo. "
        "Respeite os tempos aproximados, gestos, postura, direção, expressões e "
        "transições. Mantenha os movimentos de câmera separados dos movimentos "
        "corporais:\n" + movements + "\n\n" + fixed_rules
    )
    return {"short": short, "detailed": detailed, "universal": detailed}

@app.get("/health")
def health():
    return {"ok": True, "service": "MotionCopy AI API"}

@app.post("/api/analyze")
async def analyze_video(video: UploadFile = File(...)):
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="A chave GEMINI_API_KEY ainda não foi configurada no servidor."
        )

    mime = (video.content_type or "").lower()
    if mime not in VIDEO_MIMES:
        raise HTTPException(
            status_code=415,
            detail="Formato não suportado. Envie MP4, MOV, WebM ou outro formato de vídeo aceito."
        )

    data = await video.read()
    if not data:
        raise HTTPException(status_code=400, detail="O arquivo está vazio.")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Vídeo maior que o limite configurado de {MAX_UPLOAD_MB} MB."
        )

    suffix = Path(video.filename or "video.mp4").suffix or ".mp4"
    temp_path = None
    uploaded = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp.write(data)
            temp_path = temp.name

        client = genai.Client(api_key=API_KEY)
        uploaded = client.files.upload(
            file=temp_path,
            config=types.UploadFileConfig(
                mime_type=mime,
                display_name="motioncopy-reference-video"
            )
        )

        # Aguarda o processamento do arquivo pelo serviço de vídeo.
        deadline = time.time() + 180
        while str(uploaded.state).upper().endswith("PROCESSING"):
            if time.time() > deadline:
                raise TimeoutError("O processamento do vídeo demorou mais que o esperado.")
            time.sleep(3)
            uploaded = client.files.get(name=uploaded.name)

        if "FAILED" in str(uploaded.state).upper():
            raise RuntimeError("O serviço de IA não conseguiu processar este vídeo.")

        response = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_uri(
                    file_uri=uploaded.uri,
                    mime_type=uploaded.mime_type or mime
                ),
                ANALYSIS_INSTRUCTIONS
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2
            )
        )

        result = extract_json(response.text)
        result["prompts"] = make_prompts(result)
        result["model"] = MODEL
        return result

    except HTTPException:
        raise
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha na análise do vídeo: {str(exc)}"
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        # O arquivo temporário enviado à API deve ser removido quando possível.
        if uploaded is not None and API_KEY:
            try:
                genai.Client(api_key=API_KEY).files.delete(name=uploaded.name)
            except Exception:
                pass
