# Datei: ~/projects/py/STT/dictation_service.py

import vosk
import sys
import sounddevice as sd
import queue
import json
import pyperclip
import subprocess
import time
from pathlib import Path
import argparse
import os

# --- Konfiguration ---
SCRIPT_DIR = Path(__file__).resolve().parent
TRIGGER_FILE = Path("/tmp/vosk_trigger")
LOG_FILE = Path("/tmp/vosk_dictation.log")
NOTIFY_SEND_PATH = "/usr/bin/notify-send"
XDOTOOL_PATH = "/usr/bin/xdotool"
SAMPLE_RATE = 16000

# --- Argumenten-Verarbeitung mit Standardwert ---
MODEL_NAME_DEFAULT = "vosk-model-de-0.21"
parser = argparse.ArgumentParser(description="A real-time dictation service using Vosk.")
parser.add_argument('--vosk_model', help=f"Name of the Vosk model folder. Defaults to '{MODEL_NAME_DEFAULT}'.")
args = parser.parse_args()
VOSK_MODEL_FILEread = ''
VOSK_MODEL_FILE = "/tmp/vosk_model"
if os.path.exists(VOSK_MODEL_FILE):
    with open(VOSK_MODEL_FILE, 'r') as f:
        VOSK_MODEL_FILEread = f.read()
MODEL_NAME = args.vosk_model or VOSK_MODEL_FILEread or MODEL_NAME_DEFAULT
MODEL_PATH = SCRIPT_DIR / MODEL_NAME

# MODEL_NAME = args.vosk_model if args.vosk_model else MODEL_NAME_DEFAULT


# --- Hilfsfunktionen ---
def notify(summary, body="", urgency="low", icon=None):
    full_cmd = [NOTIFY_SEND_PATH, "-r", "9999", "-u", urgency, summary, body, "-t", "2000"]
    if icon:
        full_cmd.extend(["-i", icon])
    try:
        subprocess.run(full_cmd, check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e1:
        basic_cmd = [NOTIFY_SEND_PATH, summary, body]
        try:
            subprocess.run(basic_cmd, check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e2:
            error_message = (
                f"{time.strftime('%Y-%m-%d %H:%M:%S')} - NOTIFICATION FAILED\n"
                f"  Summary: {summary}\n  Body: {body}\n  Full command error: {e1}\n  Basic command error: {e2}\n"
                "------------------------------------------\n"
            )
            print(error_message)
            with open(LOG_FILE, "a") as f: f.write(error_message)


def transcribe_audio_with_feedback(recognizer):
    q = queue.Queue()
    def audio_callback(indata, frames, time, status):
        if status: print(status, file=sys.stderr)
        q.put(bytes(indata))

    recognizer.SetWords(True)
    try:
        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=4000,
                               dtype='int16', channels=1, callback=audio_callback):
            notify("Vosk Hört zu...", "Jetzt sprechen.", "normal", icon="microphone-sensitivity-high-symbolic")
            while True:
                data = q.get()
                if recognizer.AcceptWaveform(data):
                    return json.loads(recognizer.Result()).get('text', '')
                else:
                    partial_text = json.loads(recognizer.PartialResult()).get('partial', '')
                    # if partial_text: notify("...", partial_text, icon="microphone-sensitivity-medium-symbolic")
    except Exception as e:
        error_msg = f"Fehler bei der Transkription: {e}"
        print(error_msg); notify("Vosk Fehler", error_msg, icon="dialog-error"); return ""

# --- Hauptlogik des Dienstes ---
print("--- Vosk Diktier-Dienst ---")

if not MODEL_PATH.exists():
    msg = f"FATALER FEHLER: Modell nicht gefunden unter {MODEL_PATH}"
    print(msg); notify("Vosk Startfehler", msg, icon="dialog-error"); sys.exit(1)

print(f"Lade Modell '{MODEL_NAME}'... Dies kann einige Sekunden dauern.")
try:
    model = vosk.Model(str(MODEL_PATH))
    print("Modell erfolgreich geladen. Dienst wartet auf Signal.")
    notify("Vosk Dienst Bereit", f"Hotkey für '{MODEL_NAME}' ist nun aktiv.", icon="media-record")
except Exception as e:
    msg = f"FATALER FEHLER: Modell konnte nicht geladen werden. {e}"
    print(msg); notify("Vosk Startfehler", msg, icon="dialog-error"); sys.exit(1)

is_recording = False

try:
    while True:
        try:
            if TRIGGER_FILE.exists() and not is_recording:
                is_recording = True
                TRIGGER_FILE.unlink()
                print("Signal erkannt! Starte Transkription.")

                try:
                    recognizer = vosk.KaldiRecognizer(model, SAMPLE_RATE)
                    recognized_text = transcribe_audio_with_feedback(recognizer) + ' '
                    if recognized_text:
                        print(f"Transkribiert: '{recognized_text}'")
                        pyperclip.copy(recognized_text)
                        subprocess.run([XDOTOOL_PATH, "type", "--clearmodifiers", recognized_text])
                        # notify("Vosk Diktat", f"Text eingefügt:\n'{recognized_text}'", "normal", icon="edit-paste")
                    else:
                        notify("Vosk Diktat", "Kein Text erkannt.", icon="dialog-warning")
                finally:
                    is_recording = False
                    notify("Vosk Diktat", "Not Recoding at the Moment.", icon="dialog-warning")

            elif TRIGGER_FILE.exists() and not is_recording:
                 TRIGGER_FILE.unlink()

            time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nDienst durch Benutzer beendet.")
            notify("Vosk Diktat", "Dienst durch Benutzer beendet.", icon="dialog-warning")
            break # Verlässt den while-Loop und geht zum finally-Block
        except Exception as e:
            error_msg = f"Fehler im Haupt-Loop: {e}"
            print(error_msg)
            notify("Vosk Dienst Fehler", error_msg, icon="dialog-error")
            is_recording = False
finally:
    print("Dienst wird heruntergefahren. Sende Abschluss-Benachrichtigung.")
    notify("Vosk Dienst", "Dienst wurde beendet.", "normal", icon="process-stop-symbolic")
