
import tkinter as tk
from tkinter import scrolledtext
import sounddevice as sd
from scipy.io.wavfile import write
import speech_recognition as sr
import google.generativeai as genai
import pyttsx3
import threading
import os

API_KEY = "chave"

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

engine = pyttsx3.init()
engine.setProperty("rate", 180)

def carregar_contexto():
    if os.path.exists("knowledge.txt"):
        with open("knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    return "Sem informações cadastradas."

def falar(texto):
    engine.say(texto)
    engine.runAndWait()

def gravar_audio():
    fs = 44100
    duracao = 5

    chat.insert(tk.END, "\n🎤 Ouvindo por 5 segundos...\n")
    chat.see(tk.END)

    audio = sd.rec(int(duracao * fs), samplerate=fs, channels=1)
    sd.wait()

    write("entrada.wav", fs, audio)

def reconhecer_audio():
    r = sr.Recognizer()

    with sr.AudioFile("entrada.wav") as source:
        audio = r.record(source)

    try:
        texto = r.recognize_google(audio, language="pt-BR")
        return texto
    except:
        return None

def responder_ia(pergunta):
    contexto = carregar_contexto()

    prompt = f"""
    Você é o MoveBus, assistente de transporte público.

    Use TODAS as informações abaixo, incluindo memórias anteriores:

    {contexto}

    Pergunta atual:
    {pergunta}

    Responda de forma clara, curta e útil.
    """

    resposta = model.generate_content(prompt)
    salvar_memoria(resposta)
    return resposta.text

def iniciar():
    thread = threading.Thread(target=processar)
    thread.start()

def processar():
    try:
        gravar_audio()

        pergunta = reconhecer_audio()

        if not pergunta:
            chat.insert(tk.END, "Não entendi o áudio.\n")
            chat.see(tk.END)
            return

        chat.insert(tk.END, f"Você: {pergunta}\n")
        chat.see(tk.END)

        resposta = responder_ia(pergunta)

        chat.insert(tk.END, f"MoveBus: {resposta}\n\n")
        chat.see(tk.END)

        falar(resposta)

    except Exception as e:
        chat.insert(tk.END, f"Erro: {e}\n")
        chat.see(tk.END)

def gerar_sumario(texto):
    prompt = f"""
    Resuma em uma frase curta e objetiva a informação abaixo:

    {texto}
    """

    resposta = model.generate_content(prompt)
    return resposta.text.strip()

def salvar_memoria(resposta):
    resumo = gerar_sumario(resposta)

    with open("knowledge.txt", "a", encoding="utf-8") as f:
        f.write("\nMEMÓRIA: " + resumo)

def enviar_texto():
    pergunta = entrada.get().strip()

    if pergunta == "":
        return

    entrada.delete(0, tk.END)

    thread = threading.Thread(target=lambda: responder_pergunta(pergunta))
    thread.start()

def responder_pergunta(pergunta):
    chat.insert(tk.END, f"Você: {pergunta}\n")
    chat.see(tk.END)

    resposta = responder_ia(pergunta)

    chat.insert(tk.END, f"MoveBus: {resposta}\n\n")
    chat.see(tk.END)

    falar(resposta)

janela = tk.Tk()
janela.title("MoveBus")
janela.geometry("650x500")
janela.resizable(False, False)

titulo = tk.Label(
    janela,
    text="🚌 MoveBus - Assistente de Transporte",
    font=("Arial", 16, "bold")
)
titulo.pack(pady=10)

chat = scrolledtext.ScrolledText(
    janela,
    width=75,
    height=22,
    font=("Arial", 10)
)
chat.pack(padx=10)

frame_texto = tk.Frame(janela)
frame_texto.pack(pady=10)

entrada = tk.Entry(
    frame_texto,
    width=55,
    font=("Arial", 12)
)
entrada.pack(side=tk.LEFT, padx=5)

btn_texto = tk.Button(
    frame_texto,
    text="📩 Enviar",
    font=("Arial", 12),
    bg="#28A745",
    fg="white",
    command=enviar_texto
)
btn_texto.pack(side=tk.LEFT)

btn = tk.Button(
    janela,
    text="🎤 Perguntar por Voz",
    font=("Arial", 14),
    bg="#1E90FF",
    fg="white",
    command=iniciar
)
btn.pack(pady=15)

janela.mainloop()
