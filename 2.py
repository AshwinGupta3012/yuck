import pjsua2 as pj


from fastapi import FastAPI, HTTPException, WebSocket


from fastapi.middleware.cors import CORSMiddleware


from pydantic import BaseModel


from typing import Dict, Set, Optional, List


from datetime import datetime


import asyncio


import json


import uuid


from dataclasses import dataclass, asdict


import threading


import uvicorn


# FastAPI setup


app = FastAPI(title="SIPREC Service")


app.add_middleware(


    CORSMiddleware,


    allow_origins=["*"],


    allow_credentials=True,


    allow_methods=["*"],


    allow_headers=["*"],


)


# Data Models


class CallData(BaseModel):


    call_id: str


    seq_id: str


    agent_dnis: str


    start_time: datetime


    audio_ports: Dict[str, int]


    codec_info: Dict[str, str]


    status: str = "active"


# Global state


active_calls: Dict[str, CallData] = {}


active_connections: Dict[str, Set[WebSocket]] = {}


ep = None  # PJSUA2 Endpoint


class RecordingCall(pj.Call):


    def __init__(self, acc, call_id=None):


        pj.Call.__init__(self, acc)


        self.call_id = call_id or str(uuid.uuid4())


        print(f"New call created with ID: {self.call_id}")


    async def notify_websockets(self, call_data: CallData):


        if call_data.agent_dnis in active_connections:


            message = {


                "event": "call_update",


                "data": call_data.dict()


            }


            for ws in active_connections[call_data.agent_dnis]:


                try:


                    await ws.send_json(message)


                    print(f"Sent update to agent {call_data.agent_dnis}")


                except Exception as e:


                    print(f"WebSocket send failed: {e}")


    def onStreamCreated(self, stream):


        print(f"Stream created for call {self.call_id}")


        if self.call_id in active_calls:


            try:


                mi = stream.getMediaInfo()


                call_data = active_calls[self.call_id]


                call_data.audio_ports[f"stream_{stream.getId()}"] = stream.getPort()


                call_data.codec_info.update({


                    "name": mi.codecInfo,


                    "clock_rate": str(mi.clockRate),


                    "channels": str(mi.channelCount)


                })


                asyncio.create_task(self.notify_websockets(call_data))


                print(f"Updated stream info: {call_data}")


            except Exception as e:


                print(f"Error in onStreamCreated: {e}")


    def onCallState(self, prm):


        try:


            ci = self.getInfo()


            state = ci.state


            print(f"Call {self.call_id} state: {state}")


            if self.call_id in active_calls:


                call_data = active_calls[self.call_id]


                if state == pj.PJSIP_INV_STATE_DISCONNECTED:


                    call_data.status = "completed"


                    asyncio.create_task(self.notify_websockets(call_data))


                    # Keep call in memory for a while for history


                    asyncio.create_task(self.cleanup_call(delay=300))  # 5 minutes


        except Exception as e:


            print(f"Error in onCallState: {e}")


    async def cleanup_call(self, delay):


        await asyncio.sleep(delay)


        if self.call_id in active_calls:


            del active_calls[self.call_id]


            print(f"Cleaned up call {self.call_id}")


class SipAccount(pj.Account):


    def onIncomingCall(self, prm):


        print("Incoming call received")


        try:


            call = RecordingCall(self)


            # Extract headers


            headers = prm.getRxHeader()


            seq_id = "unknown"


            agent_dnis = "unknown"


            for header in headers:


                if "X-Sequence-ID" in header:


                    seq_id = header.split(":")[1].strip()


                elif "X-Agent-DNIS" in header:


                    agent_dnis = header.split(":")[1].strip()


            # Create call data


            call_data = CallData(


                call_id=call.call_id,


                seq_id=seq_id,


                agent_dnis=agent_dnis,


                start_time=datetime.now(),


                audio_ports={},


                codec_info={},


                status="active"


            )


            active_calls[call.call_id] = call_data


            asyncio.create_task(call.notify_websockets(call_data))


            print(f"Call stored: {call_data}")


            # Auto-answer call


            call_prm = pj.CallOpParam()


            call_prm.statusCode = 200


            call.answer(call_prm)


        except Exception as e:


            print(f"Error in onIncomingCall: {e}")


def init_pjsua():


    global ep


    try:


        # Create endpoint


        ep = pj.Endpoint()


        ep.libCreate()


        # Configure endpoint


        ep_cfg = pj.EpConfig()


        ep_cfg.uaConfig.maxCalls = 32


        ep_cfg.medConfig.enableIce = False


        ep_cfg.medConfig.enableRtcp = True


        # Initialize endpoint


        ep.libInit(ep_cfg)


        # Create transport


        sipTpConfig = pj.TransportConfig()


        sipTpConfig.port = 5060


        ep.transportCreate(pj.PJSIP_TRANSPORT_TCP, sipTpConfig)


        # Start PJSUA2


        ep.libStart()


        # Account configuration


        acc_cfg = pj.AccountConfig()


        acc_cfg.idUri = "sip:recorder@localhost"


        acc_cfg.regConfig.registrarUri = "sip:your_sbc_ip:5060"


        # Create account


        acc = SipAccount()


        acc.create(acc_cfg)


        print("PJSUA2 initialized successfully")


        return True


    except Exception as e:


        print(f"Error initializing PJSUA2: {e}")


        return False


# WebSocket endpoint


@app.websocket("/ws/agent/{agent_dnis}")


async def agent_stream(websocket: WebSocket, agent_dnis: str):


    await websocket.accept()


    print(f"WebSocket connected for agent {agent_dnis}")


    if agent_dnis not in active_connections:


        active_connections[agent_dnis] = set()


    active_connections[agent_dnis].add(websocket)


    try:


        # Send initial state


        agent_calls = {


            call_id: call_data.dict()


            for call_id, call_data in active_calls.items()


            if call_data.agent_dnis == agent_dnis


        }


        await websocket.send_json({


            "event": "initial_state",


            "data": agent_calls


        })


        # Keep connection alive


        while True:


            data = await websocket.receive_text()


            if data == "ping":


                await websocket.send_text("pong")


    except Exception as e:


        print(f"WebSocket error: {e}")


    finally:


        active_connections[agent_dnis].remove(websocket)


        if not active_connections[agent_dnis]:


            del active_connections[agent_dnis]


        print(f"WebSocket disconnected for agent {agent_dnis}")


# REST endpoints


@app.get("/calls")


async def get_calls():


    """Get all active calls"""


    return {"calls": {k: v.dict() for k, v in active_calls.items()}}


@app.get("/calls/{call_id}")


async def get_call(call_id: str):


    """Get specific call details"""


    if call_id not in active_calls:


        raise HTTPException(status_code=404, detail="Call not found")


    return active_calls[call_id]


@app.get("/calls/agent/{agent_dnis}")


async def get_agent_calls(agent_dnis: str):


    """Get all calls for specific agent"""


    agent_calls = {


        call_id: call_data 


        for call_id, call_data in active_calls.items() 


        if call_data.agent_dnis == agent_dnis


    }


    return {"agent_calls": agent_calls}


@app.get("/health")


async def health_check():


    """Service health check"""


    if ep and ep.libIsThreadRegistered():


        return {"status": "healthy"}


    return {"status": "unhealthy"}


# Startup and shutdown events


@app.on_event("startup")


async def startup_event():


    if not init_pjsua():


        raise Exception("Failed to initialize PJSUA2")


@app.on_event("shutdown")


async def shutdown_event():


    if ep:


        ep.libDestroy()


        print("PJSUA2 shutdown complete")


if __name__ == "__main__":


    uvicorn.run(app, host="0.0.0.0", port=8000)
 
class RecordingCall(pj.Call):


    def __init__(self, acc, call_id=None):


        pj.Call.__init__(self, acc)


        self.call_id = call_id or str(uuid.uuid4())


        self.recording_started = False


        print(f"New call created with ID: {self.call_id}")


    def onCallState(self, prm):


        try:


            ci = self.getInfo()


            state = ci.state


            print(f"Call {self.call_id} state: {state}")


            if state == pj.PJSIP_INV_STATE_INCOMING:


                # Send 100 Trying immediately


                call_prm = pj.CallOpParam()


                call_prm.statusCode = 100  # Trying


                self.answer(call_prm)


                print(f"Sent 100 Trying for call {self.call_id}")


            elif state == pj.PJSIP_INV_STATE_EARLY:


                # Send 180 Ringing


                call_prm = pj.CallOpParam()


                call_prm.statusCode = 180  # Ringing


                self.answer(call_prm)


                print(f"Sent 180 Ringing for call {self.call_id}")


            elif state == pj.PJSIP_INV_STATE_CONNECTING:


                if not self.recording_started:


                    # Send 200 OK and start recording


                    call_prm = pj.CallOpParam()


                    call_prm.statusCode = 200  # OK


                    self.answer(call_prm)


                    self.recording_started = True


                    print(f"Sent 200 OK and started recording for call {self.call_id}")


            elif state == pj.PJSIP_INV_STATE_DISCONNECTED:


                # Call ended


                if self.call_id in active_calls:


                    call_data = active_calls[self.call_id]


                    call_data.status = "completed"


                    asyncio.create_task(self.notify_websockets(call_data))


                    asyncio.create_task(self.cleanup_call(delay=300))


                print(f"Call {self.call_id} disconnected")


        except Exception as e:


            print(f"Error in onCallState: {e}")


    def onStreamCreated(self, stream):


        print(f"Stream created for call {self.call_id}")


        try:


            mi = stream.getMediaInfo()


            if self.call_id in active_calls:


                call_data = active_calls[self.call_id]


                # Configure stream


                stream_cfg = pj.MediaStreamConfig()


                stream_cfg.enableEc = False  # Disable echo cancellation for recording


                stream_cfg.enableVad = False  # Disable voice activity detection


                stream.start(stream_cfg)


                # Store stream info


                stream_id = f"stream_{stream.getId()}"


                call_data.audio_ports[stream_id] = stream.getPort()


                call_data.codec_info.update({


                    "name": mi.codecInfo,


                    "clock_rate": str(mi.clockRate),


                    "channels": str(mi.channelCount),


                    "stream_id": stream_id,


                    "direction": "recording"


                })


                asyncio.create_task(self.notify_websockets(call_data))


                print(f"Started recording stream: {stream_id} for call {self.call_id}")


        except Exception as e:


            print(f"Error configuring stream: {e}")


class SipAccount(pj.Account):


    def onIncomingCall(self, prm):


        print("Incoming SIPREC call received")


        try:


            # Create new call instance


            call = RecordingCall(self)


            # Send immediate 100 Trying


            callOpParam = pj.CallOpParam()


            callOpParam.statusCode = 100


            call.answer(callOpParam)


            # Extract headers


            headers = prm.getRxHeader()


            seq_id = "unknown"


            agent_dnis = "unknown"


            for header in headers:


                if "X-Sequence-ID" in header:


                    seq_id = header.split(":")[1].strip()


                elif "X-Agent-DNIS" in header:


                    agent_dnis = header.split(":")[1].strip()


            # Create initial call data


            call_data = CallData(


                call_id=call.call_id,


                seq_id=seq_id,


                agent_dnis=agent_dnis,


                start_time=datetime.now(),


                audio_ports={},


                codec_info={},


                status="establishing"


            )


            active_calls[call.call_id] = call_data


            asyncio.create_task(call.notify_websockets(call_data))


            print(f"Call establishment in progress: {call_data}")


            # Let call proceed to onCallState for further processing


        except Exception as e:


            print(f"Error handling incoming call: {e}")


            # Send 500 if something went wrong


            callOpParam = pj.CallOpParam()


            callOpParam.statusCode = 500


            call.answer(callOpParam)
 