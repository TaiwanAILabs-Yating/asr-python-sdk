from abc import ABC, abstractclassmethod
import wave
from pyaudio import PyAudio, paComplete, paContinue, paInt16
import json
import websocket
from .ASRResultHandleStrategy import DefaultASRResultHandleStrategy

class WavStreamer():
  __wave_file = None
  
  def __init__(self, ws, input_wav: str = None) -> None:
    self.__ws = ws
    self.__pa = PyAudio()
    self.__input_wav = input_wav
    self.__stream = self.__create_stream()
  
  def start(self):
    self.__stream.start_stream()
    print("### start stream ###")
    
  def close(self):
    if self.__stream:
      self.__stream.stop_stream()
      self.__stream.close()
    if self.__pa:
      self.__pa.terminate()
    if self.__wave_file:
      self.__wave_file.close()
    
  def __create_stream(self):
    pa = self.__pa
    if self.__input_wav:
      self.__wave_file = wave.open(self.__input_wav, 'rb')
      return pa.open(format=paInt16, channels=1, rate=16000, output=True,
                      stream_callback=self.__cb_wav)
    else:
      return pa.open(format=paInt16, channels=1, rate=16000, input=True,
                      stream_callback=self.__cb)
      
  def __cb(self, in_data, frame_count, time_info, status_flags):
    self.__ws.send(in_data, opcode=0x2)
    if in_data:
        print(in_data)
    return (in_data, paContinue)

  def __cb_wav(self, in_data, frame_count, time_info, status_flags):
    if in_data:
      print(len(in_data))
    data = self.__wave_file.readframes(frame_count)
    self.__ws.send(data, opcode=0x2)

    if frame_count * 2 > len(data):
      self.__ws.send('', opcode=0x2)
      return (data, paComplete)
    return (data, paContinue)
  
class AbstractClient(ABC):
  on_processing_sentence = None
  on_final_sentence = None
  
  def __init__(self, args):
    self.args = args
    self.websocket_url = self.args['websocket_url']
    self.__streamer = None
    self._ws = None
    self.__default_asr_result_handler = DefaultASRResultHandleStrategy()

  @property
  def ws(self):
      return self._ws

  @ws.setter
  def ws(self, ws):
      self._ws = ws

  @ws.getter
  def ws(self):
      return self._ws

  def init_websocket(self, token):
    self.ws = websocket.WebSocketApp(
      f'{self.websocket_url}?token={token}',
      on_message=self._on_message,
      on_error=self._on_error,
      on_close=self._on_close,
      on_open=self._on_open
    )
  
  def run(self):
    self.ws.run_forever()

  @abstractclassmethod
  def _on_message(self, ws, message):
    pass

  def _on_error(self, ws, error):
    print(error)

  def _on_close(self, ws, close_status_code, close_msg):
    if self.__streamer:
      self.__streamer.close()
    print("### closed ###")
    print(f'Websocket closed[{close_status_code}]: {close_msg}')

  def _on_open(self, ws):
    if 'audio_url' not in self.args:
      self.__streamer = WavStreamer(self.ws, self.args['input_wav'])
      if 'j2' not in self.args:
        self.__streamer.start()
    print("### opened ###")

  def _lang_switch(self, lang_code):
    print(f'lang switch: {lang_code}')
    data = {
      'pipe': {
        'config': {
          'liveStreamingCodeSwitch': lang_code
        }
      } 
    }
    self.ws.send(json.dumps(data))

  def _handle_asr_result(self, message):
    if 'asr_final' in message['pipe']:
      if self.on_final_sentence:
        self.on_final_sentence(message)
      else:
        self.__default_asr_result_handler.on_final_sentence(message)
    else:
      if self.on_processing_sentence:
        self.on_processing_sentence(message)
      else:
        self.__default_asr_result_handler.on_processing_sentence(message)