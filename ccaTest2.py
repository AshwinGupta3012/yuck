import pjsua2 as pj
import wave
import time
import os
import concurrent.futures
from datetime import datetime
import json

class MyLogWriter(pj.LogWriter):
    def write(self, entry):
        print(f"Log: {entry}")


class MyCall(pj.Call):
    def __init__(self, acc, call_id=None):
        super().__init__(acc, call_id)
        self.account = acc
        self.rtp_streaming = False

    def onCallState(self, prm):
        call_info = self.getInfo()
        print(f"Call {call_info.remoteUri} state: {call_info.stateText}")
        if call_info.state == pj.PJSIP_INV_STATE_CONFIRMED:
            print(f"Call confirmed with {call_info.remoteUri}")
            self.start_rtp()

        elif call_info.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            print(f"Call disconnected with {call_info.remoteUri}")
            self.stop_rtp()

    def onCallMediaState(self, prm):
        call_info = self.getInfo()
        if call_info.state == pj.PJSIP_INV_STATE_CONFIRMED:
            print("Media state confirmed")

    def start_rtp(self):
        self.rtp_streaming = True
        print("RTP streaming started")

    def stop_rtp(self):
        self.rtp_streaming = False
        print("RTP streaming stopped")


class MyAccount(pj.Account):
    def onRegState(self, prm):
        print(f"Registration status: {prm.code} - {prm.reason}")

    def create_call(self, target_uri):
        call = MyCall(self)
        call_prm = pj.CallOpParam()
        call.makeCall(target_uri, call_prm)
        return call

# Initialize pjsua2
def initialize_pjsua2():
    ep = pj.Endpoint()
    ep.libCreate()

    # Configure logging
    log_cfg = pj.LogConfig()
    log_cfg.consoleLevel = 4  # Set log level (0-5, where 5 is the most verbose)
    log_cfg.writer = MyLogWriter()  # Ensure writer is an instance of LogWriter

    # Configure the endpoint
    ep_cfg = pj.EpConfig()
    ep_cfg.logConfig = log_cfg

    # Initialize the library with the configuration
    ep.libInit(ep_cfg)

    # Create a UDP transport for SIP
    transport_cfg = pj.TransportConfig()
    transport_cfg.port = 5070  # Local SIP signaling port
    ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, transport_cfg)

    # Start the PJSUA2 library
    ep.libStart()
    print("SIP service started on localhost, ready to send and receive SIP messages.")
    return ep


def setup_account(ep, username, password, proxy):
    account_cfg = pj.AccountConfig()
    account_cfg.idUri = f"sip:{username}@{proxy}"
    account_cfg.regConfig.registerOnAdd = False

    cred = pj.AuthCredInfo("digest", "*", username, 0, password)
    account_cfg.sipConfig.authCreds.append(cred)
    account_cfg.sipConfig.proxies.append(f"sip:{proxy}")

    acc = MyAccount()
    acc.create(account_cfg)
    return acc


def stream_audio(call, audio_file):
    try:
        with wave.open(audio_file, 'rb') as wf:
            frame_rate = wf.getframerate()
            chunk_size = 16384

            while True:
                if not call.rtp_streaming:
                    break
                data = wf.readframes(chunk_size)
                if not data:
                    break
                time.sleep(chunk_size / frame_rate)
    except Exception as e:
        print(f"Error streaming audio: {e}")


def process_sip_signals(ep, acc, sip_signals):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        for folder_path, sip_signal_list in sip_signals.items():
            audio_files = [f for f in os.listdir(folder_path) if f.endswith('.wav')]
            for index, audio_file in enumerate(audio_files):
                audio_file_path = os.path.join(folder_path, audio_file)
                sip_uri = sip_signal_list[index % len(sip_signal_list)]
                futures.append(executor.submit(handle_call, acc, sip_uri, audio_file_path))

        for future in concurrent.futures.as_completed(futures):
            future.result()


def handle_call(acc, target_uri, audio_file):
    print(f"Initiating call to {target_uri} with audio file {audio_file}")
    call = acc.create_call(target_uri)
    time.sleep(2)  # Allow time for the call to connect

    if call.rtp_streaming:
        stream_audio(call, audio_file)

    # End the call
    call.hangup(pj.CallOpParam())
    print(f"Call to {target_uri} completed")


def load_sip_signals(json_file):
    try:
        with open(json_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        return {}


def main():
    json_file = "/home/aiadmin/yuck/SIPjson.json"
    sip_signals = load_sip_signals(json_file)

    if not sip_signals:
        print("No SIP signals found. Please check the JSON file.")
        return

    ep = initialize_pjsua2()
    acc = setup_account(ep, "user", "password", "proxy.domain")

    try:
        process_sip_signals(ep, acc, sip_signals)
    finally:
        acc.delete()
        ep.libDestroy()

    print("All calls processed successfully")


if __name__ == "__main__":
    main()
