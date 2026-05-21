import tkinter as tk
from tkinter import scrolledtext, font as tkfont
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
import speech_recognition as sr
import google.generativeai as genai
import pyttsx3
import threading
import queue
import os
import datetime

# Configuração da API
API_KEY = "sua_chave_vai_aqui"
KNOWLEDGE_FILE = "knowledge.txt"
AUDIO_FILE = "entrada.wav"

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# Motor de voz — thread dedicada + fila

_tts_queue: queue.Queue = queue.Queue()

def _tts_worker() -> None:
    """Thread dedicada ao pyttsx3. Fica viva enquanto o programa roda."""
    eng = pyttsx3.init()
    eng.setProperty("voice", r'HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\Tokens\TTS_MS_PT-BR_MARIA_11.0')
    eng.setProperty("rate", 250)
    eng.setProperty("volume", 1.3)
    while True:
        texto = _tts_queue.get()        # bloqueia até ter algo na fila
        if texto is None:               # sinal de encerramento
            break
        try:
            eng.say(texto)
            eng.runAndWait()
        except Exception as e:
            print(f"[TTS] Erro ao falar: {e}")
        finally:
            _tts_queue.task_done()

_tts_thread = threading.Thread(target=_tts_worker, daemon=True, name="TTS-Worker")
_tts_thread.start()


# CAMADA DE CONHECIMENTO (RAG simples via arquivo)
def carregar_contexto() -> str:
    """Lê o arquivo de conhecimento/memória."""
    if os.path.exists(KNOWLEDGE_FILE):
        with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return "Sem informações cadastradas."


def salvar_memoria(resposta_texto: str) -> None:
    """Gera um resumo da resposta e salva no arquivo de conhecimento."""
    try:
        resumo = gerar_sumario(resposta_texto)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(KNOWLEDGE_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n[{timestamp}] MEMÓRIA: {resumo}")
    except Exception as e:
        print(f"[AVISO] Não foi possível salvar memória: {e}")


def gerar_sumario(texto: str) -> str:
    """Pede ao modelo um resumo de uma linha."""
    prompt = (
        "Resuma em UMA frase curta e objetiva a informação abaixo, "
        "sem introdução e sem pontuação final:\n\n" + texto
    )
    resposta = model.generate_content(prompt)
    return resposta.text.strip()


# CAMADA DE IA

SYSTEM_PROMPT = """Você é o MoveBus, assistente inteligente de transporte público.
Seu objetivo é ajudar pessoas a encontrarem informações sobre linhas de ônibus,
horários, itinerários e dicas de mobilidade urbana.

Regras:
- Responda de forma clara, objetiva e amigável.
- Se não souber algo, diga honestamente e sugira onde buscar a informação.
- Priorize as informações do contexto fornecido antes de usar conhecimento geral.
"""

def responder_ia(pergunta: str) -> str:
    """Monta o prompt RAG e obtém resposta do modelo."""
    contexto = carregar_contexto()

    prompt = f"""{SYSTEM_PROMPT}

--- CONTEXTO / MEMÓRIAS ANTERIORES ---
{contexto}
--- FIM DO CONTEXTO ---

Pergunta do usuário: {pergunta}
"""

    resposta = model.generate_content(prompt)
    texto = resposta.text.strip()
    salvar_memoria(texto)
    return texto


# CAMADA DE ÁUDIO

FS = 16000
CANAIS = 1


def gravar_audio() -> None:
    """
    Grava áudio continuamente até o usuário clicar novamente.
    """

    global _gravando

    adicionar_mensagem_sistema("🎤 Gravando... clique novamente para parar.")

    audio_frames = []

    stream = sd.InputStream(
        samplerate=FS,
        channels=CANAIS,
        dtype="float32"
    )

    with stream:
        while _gravando:
            data, overflowed = stream.read(1024)

            if overflowed:
                print("Overflow detectado")

            audio_frames.append(data.copy())

    if not audio_frames:
        return

    audio_f32 = np.concatenate(audio_frames, axis=0)

    audio_i16 = np.clip(audio_f32, -1.0, 1.0)
    audio_i16 = (audio_i16 * 32767).astype(np.int16)

    write(AUDIO_FILE, FS, audio_i16)


def reconhecer_audio() -> str | None:
    """Transcreve o arquivo WAV gravado usando Google Speech Recognition."""
    r = sr.Recognizer()
    with sr.AudioFile(AUDIO_FILE) as source:
        r.adjust_for_ambient_noise(source, duration=0.3)
        audio = r.record(source)
    try:
        return r.recognize_google(audio, language="pt-BR")
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        adicionar_mensagem_sistema(f"⚠️ Erro no serviço de voz: {e}")
        return None


# CAMADA DE TEXT-TO-SPEECH

def falar(texto: str) -> None:
    """Enfileira o texto para ser falado pela thread dedicada de TTS."""
    _tts_queue.put(texto)

# INTERFACE GRÁFICA

COR_BG       = "#0D1B2A"   # azul-escuro (fundo)
COR_PAINEL   = "#112233"   # painel de chat
COR_ENTRADA  = "#162840"   # campo de texto
COR_BTN_VOZ  = "#1E90FF"   # azul brilhante
COR_BTN_ENV  = "#28A745"   # verde
COR_TEXTO    = "#E8F0F7"   # branco-azulado
COR_USER     = "#60AFFF"   # azul claro (balão do usuário)
COR_BOT      = "#7FFFB0"   # verde-menta (balão do bot)
COR_SYS      = "#FFA07A"   # laranja suave (mensagens do sistema)

_gravando = False           

def adicionar_mensagem_sistema(msg: str) -> None:
    """Insere uma linha de status no chat (thread-safe via after)."""
    janela.after(0, lambda: _inserir(f"[{msg}]\n", COR_SYS))


def _inserir(texto: str, cor: str) -> None:
    chat.configure(state="normal")
    chat.insert(tk.END, texto, cor)
    chat.see(tk.END)
    chat.configure(state="disabled")


def exibir_mensagem(remetente: str, texto: str) -> None:
    cor = COR_USER if remetente == "Você" else COR_BOT
    janela.after(0, lambda: _inserir(f"{remetente}: {texto}\n\n", cor))


# Fluxo de voz

def iniciar_voz() -> None:
    global _gravando

    # Se já estiver gravando -> para
    if _gravando:
        _gravando = False

        btn_voz.configure(
            text="⏳ Processando...",
            bg="#444444",
            state="disabled"
        )

        return

    # Se NÃO estiver gravando -> inicia
    _gravando = True

    btn_voz.configure(
        text="⏹ Parar Gravação",
        bg="#CC3333"
    )

    threading.Thread(target=_processar_voz, daemon=True).start()


def _processar_voz() -> None:
    global _gravando
    try:
        gravar_audio()
        adicionar_mensagem_sistema("🔍 Reconhecendo fala…")

        pergunta = reconhecer_audio()

        if not pergunta:
            adicionar_mensagem_sistema("Não consegui entender o áudio. Tente novamente.")
            return

        exibir_mensagem("Você", pergunta)
        _buscar_e_responder(pergunta)

    except Exception as e:
        adicionar_mensagem_sistema(f"Erro: {e}")
    finally:
        janela.after(
        0,
        lambda: btn_voz.configure(
            state="normal",
            text="🎤 Perguntar por Voz",
            bg=COR_BTN_VOZ
        )
    )


# Fluxo de texto

def enviar_texto(event=None) -> None:
    pergunta = entrada.get().strip()
    if not pergunta:
        return
    entrada.delete(0, tk.END)
    exibir_mensagem("Você", pergunta)
    threading.Thread(target=_buscar_e_responder, args=(pergunta,), daemon=True).start()


# Núcleo compartilhado

def _buscar_e_responder(pergunta: str) -> None:
    adicionar_mensagem_sistema("⏳ Consultando MoveBus…")
    try:
        resposta = responder_ia(pergunta)
        exibir_mensagem("MoveBus", resposta)
        falar(resposta)
    except Exception as e:
        adicionar_mensagem_sistema(f"❌ Erro ao consultar IA: {e}")


# CONSTRUÇÃO DA JANELA

janela = tk.Tk()
janela.title("MoveBus — Assistente de Transporte Público")
janela.geometry("680x560")
janela.resizable(False, False)
janela.configure(bg=COR_BG)

# Título
frame_titulo = tk.Frame(janela, bg=COR_BG)
frame_titulo.pack(fill="x", padx=20, pady=(14, 4))

tk.Label(
    frame_titulo,
    text="MoveBus",
    font=("Segoe UI", 20, "bold"),
    bg=COR_BG,
    fg=COR_BTN_VOZ,
).pack(side="left")

tk.Label(
    frame_titulo,
    text="Assistente de Transporte Público",
    font=("Segoe UI", 11),
    bg=COR_BG,
    fg="#7090AA",
).pack(side="left", padx=10, pady=4)

# Área de chat
chat = scrolledtext.ScrolledText(
    janela,
    width=76,
    height=22,
    font=("Consolas", 10),
    bg=COR_PAINEL,
    fg=COR_TEXTO,
    insertbackground=COR_TEXTO,
    relief="flat",
    borderwidth=0,
    state="disabled",
    wrap="word",
)
chat.pack(padx=16, pady=(0, 8))

# Tags de cor para os diferentes remetentes
chat.tag_configure(COR_USER, foreground=COR_USER)
chat.tag_configure(COR_BOT,  foreground=COR_BOT)
chat.tag_configure(COR_SYS,  foreground=COR_SYS)

# Mensagem de boas-vindas
janela.after(
    200,
    lambda: _inserir(
        "MoveBus: Olá! Sou o MoveBus! Posso te ajudar com informações "
        "sobre linhas, horários e itinerários de ônibus.\n"
        "Como posso lhe ajudar hoje?\n\n",
        COR_BOT,
    ),
)

# Campo de entrada de texto
frame_entrada = tk.Frame(janela, bg=COR_BG)
frame_entrada.pack(fill="x", padx=16, pady=(0, 8))

entrada = tk.Entry(
    frame_entrada,
    font=("Segoe UI", 12),
    bg=COR_ENTRADA,
    fg=COR_TEXTO,
    insertbackground=COR_TEXTO,
    relief="flat",
    bd=6,
)
entrada.pack(side="left", fill="x", expand=True, ipady=4)
entrada.bind("<Return>", enviar_texto)          # Enter envia mensagem

btn_enviar = tk.Button(
    frame_entrada,
    text="Enviar ➤",
    font=("Segoe UI", 11, "bold"),
    bg=COR_BTN_ENV,
    fg="white",
    activebackground="#1E7E34",
    relief="flat",
    padx=14,
    pady=4,
    cursor="hand2",
    command=enviar_texto,
)
btn_enviar.pack(side="left", padx=(8, 0))

# Botão de voz
btn_voz = tk.Button(
    janela,
    text="🎤 Perguntar por Voz",
    font=("Segoe UI", 13, "bold"),
    bg=COR_BTN_VOZ,
    fg="white",
    activebackground="#1570CC",
    relief="flat",
    padx=20,
    pady=8,
    cursor="hand2",
    command=iniciar_voz,
)
btn_voz.pack(pady=(0, 16))

# Rodapé
tk.Label(
    janela,
    text="Powered by Gemini + Google Speech Recognition  •  RAG local",
    font=("Segoe UI", 8),
    bg=COR_BG,
    fg="#445566",
).pack(side="bottom", pady=4)

# Encerramento limpo

def _ao_fechar() -> None:
    """Encerra a thread TTS antes de destruir a janela."""
    _tts_queue.put(None)   # sinal de parada para o worker
    janela.destroy()

janela.protocol("WM_DELETE_WINDOW", _ao_fechar)

janela.mainloop()