import pjsua2 as pj

class MyCall(pj.Call):
    def __init__(self, account, call_id=None):
        if call_id is None:
            super().__init__(account)
        else:
            super().__init__(account, call_id)

    def onCallState(self, prm):
        call_info = self.getInfo()
        print(f"Call {call_info.callId} state: {call_info.stateText}")

    def onCallMediaState(self, prm):
        print("Media state changed.")

def register_thread():
    if not hasattr(register_thread, "is_registered"):
        pj.ThreadRegister("MyThread", None)
        register_thread.is_registered = True

def create_call(account, target_uri):
    call = MyCall(account)
    call_prm = pj.CallOpParam()
    call.makeCall(target_uri, call_prm)
    print(f"Call to {target_uri} initiated.")
    return call

def main():
    ep = pj.Endpoint()
    ep.libCreate()

    try:
        # Initialize endpoint
        ep_cfg = pj.EpConfig()
        log_cfg = pj.LogConfig()
        log_cfg.level = 5
        log_cfg.consoleLevel = 5
        ep_cfg.logConfig = log_cfg
        ep.libInit(ep_cfg)

        # Create transport
        transport_cfg = pj.TransportConfig()
        transport_cfg.port = 3030
        ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, transport_cfg)

        # Start the library
        ep.libStart()
        print("PJSUA2 library started.")

        # Create account
        acc_cfg = pj.AccountConfig()
        acc_cfg.idUri = "sip:username@10.1.0.4"
        acc_cfg.regConfig.registrarUri = "sip:10.1.0.4:60102"
        cred = pj.AuthCredInfo("digest", "*", "username", 0, "password")
        acc_cfg.sipConfig.authCreds.append(cred)

        # Instantiate and register the account
        account = pj.Account()
        account.create(acc_cfg)
        print("Account registered.")

        # Wait for SIP events or implement call handling logic here
        print("Press Ctrl+C to quit.")
        while True:
            pass  # Replace with actual call handling logic if necessary

    except Exception as e:
        print(f"Error: {e}")
    finally:
        ep.libDestroy()
        print("PJSUA2 library destroyed.")

if __name__ == "__main__":
    main()