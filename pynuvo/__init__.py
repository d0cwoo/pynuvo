import functools
import logging
import re
import io
import serial
import string
import time
import asyncio
from functools import wraps
from threading import RLock

_LOGGER = logging.getLogger(__name__)
#logging.basicConfig(format='%(asctime)s;%(levelname)s:%(message)s', level=logging.DEBUG

'''
#Zx,ON,SRCs,VOLyy,DNDd,LOCKl<CR><LF>
'''
GRAND_CONCERTO_PWR_ON_PATTERN = re.compile('#Z(?P<zone>\d),'
                     '(?P<power>ON),'
                     'SRC(?P<source>\d),'
                     'VOL(?P<volume>\d\d),'
                     'DND(?P<dnd>\d),'
                     'LOCK(?P<lock>\d)')

'''
#Zx,OFF<CR><LF>
'''
GRAND_CONCERTO_PWR_OFF_PATTERN = re.compile('#Z(?P<zone>\d),'
                     '(?P<power>OFF)')

'''
#Zx,ON,SRCs,MUTE,DNDd,LOCKl<CR><LF>
'''
GRAND_CONCERTO_MUTE_PATTERN = re.compile('#Z(?P<zone>\d),'
                     '(?P<power>ON),'
                     'SRC(?P<source>\d),'
                     '(?P<volume>MUTE),'
                     'DND(?P<dnd>\d),'
                     'LOCK(?P<lock>\d)')

#'''
##Z0xPWRppp,SRCs,VOL-yy<CR>
#'''
#CONCERTO_PATTERN = re.compile('Z0(?P<zone>\d)'
#                     'PWR(?P<power>ON|OFF),'
#                     'SRC(?P<source>\d),'
#                     'VOL(?P<volume>-\d\d|MT)')



#'''
#Z0xPWRppp,SRCs,GRPt,VOL-yy<CR>
#'''
#SIMPLESE_PATTERN = re.compile('Z0(?P<zone>\d)'
#                     'PWR(?P<power>ON|OFF),'
#                     'SRC(?P<source>\d),'
#                     'GRP(?P<group>0|1),'
#                     'VOL(?P<volume>-\d\d|MT|XM)')


#'''
#Z02STR+"TUNER"
#'''
#SOURCE_PATTERN = re.compile('Z0(?P<zone>\d)'
#                     'STR\+\"(?P<name>.*)\"')


EOL = b'\r\n'
TIMEOUT_OP       = 0.2   # Number of seconds before serial operation timeout
TIMEOUT_RESPONSE = 2.5   # Number of seconds before command response timeout
VOLUME_DEFAULT  = 60    # Value used when zone is muted or otherwise unable to get volume integer

class ZoneStatus(object):
    def __init__(self
                 ,zone: int
                 ,power: str
                 ,source: int = '1'
                 ,volume: int = '60'
                 ,dnd: int = '0'
                 ,lock: int = '0'
                 ):
        self.zone = zone
        self.source = source
        if 'ON' in power:
           self.power = bool(1)
        else:
           self.power = bool(0)
        if 'MUTE' in volume:
           self.mute = bool(1)
           self.volume = None
        else:
           self.mute = bool(0)
           self.volume = volume
#        self.treble = 0
#        self.bass = 0
        
#        _LOGGER.debug('power - %s' , power)
#        _LOGGER.debug('source - %s' , source)
#        _LOGGER.debug('volume - %s' , volume)
#        _LOGGER.debug('dnd - %s' , dnd)
#        _LOGGER.debug('lock - %s' , lock)
#        _LOGGER.debug('mute - %s' , mute)

    @classmethod
    def from_string(cls, string: bytes):
        if not string:
            return None
#        _LOGGER.debug('string passed to ZoneStatus.from_string - %s' , string)

        match = _parse_response(string)
        
        if not match:
            return None

        try:
 #          _LOGGER.debug('match.groups =- %s' , match.groups())
           rtn = ZoneStatus(*[str(m) for m in match.groups()])
           #rtn = ZoneStatus(match.groups())
        except:
           rtn = None
  #      _LOGGER.debug('ZoneStatus rtn - %s' , rtn)
        return rtn

class Nuvo(object):
    """
    Nuvo amplifier interface
    """

    def zone_status(self, zone: int):
        """
        Get the structure representing the status of the zone
        :param zone: zone 1.12
        :return: status of the zone or None
        """
        raise NotImplemented()

    def set_power(self, zone: int, power: bool):
        """
        Turn zone on or off
        :param zone: zone 1.12        
        :param power: True to turn on, False to turn off
        """
        raise NotImplemented()

    def set_mute(self, zone: int, mute: bool):
        """
        Mute zone on or off
        :param zone: zone 1.12        
        :param mute: True to mute, False to unmute
        """
        raise NotImplemented()

    def set_volume(self, zone: int, volume: float):
        """
        Set volume for zone
        :param zone: zone 1.12        
        :param volume: float from 79(min) to 0(max) inclusive
        """
        raise NotImplemented()

    def set_treble(self, zone: int, treble: float):
        """
        Set treble for zone
        :param zone: zone 1.12        
        :param treble: float from -12 to 12 inclusive
        """
        raise NotImplemented()

    def set_bass(self, zone: int, bass: int):
        """
        Set bass for zone
        :param zone: zone 1.12        
        :param bass: float from -12 to 12 inclusive 
        """
        raise NotImplemented()

    def set_source(self, zone: int, source: int):
        """
        Set source for zone
        :param zone: zone 1.6        
        :param source: integer from 1 to 6 inclusive
        """
        raise NotImplemented()

    def restore_zone(self, status: ZoneStatus):
        """
        Restores zone to it's previous state
        :param status: zone state to restore
        """
        raise NotImplemented()


# Helpers

def _is_int(s):
    try: 
        int(s)
        return True
    except ValueError:
        return False

def _parse_response(string: bytes):
   """
   :param request: request that is sent to the nuvo
   :return: regular expression return match(s) 
   """
   match = re.search(GRAND_CONCERTO_PWR_ON_PATTERN, string)
   if match:
#      _LOGGER.debug('GRAND_CONCERTO_PWR_ON_PATTERN - Match - %s', match)
      return match

   if not match:
      match = re.search(GRAND_CONCERTO_PWR_OFF_PATTERN, string)
      if match:
#        _LOGGER.debug('GRAND_CONCERTO_PWR_OFF_PATTERN - Match - %s', match)
        return match

   if not match:
      match = re.search(GRAND_CONCERTO_MUTE_PATTERN, string)
      if match:
#        _LOGGER.debug('GRAND_CONCERTO_MUTE_PATTERN - Match - %s', match)
        return match

   if not match:
       _LOGGER.debug('NO MATCH - %s' , string)
   return None

def _format_zone_status_request(zone: int) -> str:
    return 'Z{}STATUS?'.format(zone)

def _format_set_power(zone: int, power: bool) -> str:
    zone = int(zone)
    if (power):
       return 'Z{}ON'.format(zone) 
    else:
       return 'Z{}OFF'.format(zone)

def _format_set_mute(zone: int, mute: bool) -> str:
    if (mute):
       return 'Z{}MUTEON'.format(int(zone))
    else:
       return 'Z{}MUTEOFF'.format(int(zone))

def _format_set_volume(zone: int, volume: int) -> str:
    if _is_int(volume):
       return 'Z{}VOL{:0=2}'.format(int(zone),int(volume))
    else:
       return None

def _format_set_treble(zone: int, treble: int) -> bytes:
    treble = int(max(12, min(treble, -12)))
    return 'Z{}TREB{:0=2}'.format(int(zone),treble)

def _format_set_bass(zone: int, bass: int) -> bytes:
    bass = int(max(12, min(bass, -12)))
    return 'Z{}BASS{:0=2}'.format(int(zone),bass)

def _format_set_source(zone: int, source: int) -> str:
    source = int(max(1, min(int(source), 6)))
    return 'Z{}SRC{}'.format(int(zone),source)

def get_nuvo(port_url):
    """
    Return synchronous version of Nuvo interface
    :param port_url: serial port, i.e. '/dev/ttyUSB0,/dev/ttyS0'
    :return: synchronous implementation of Nuvo interface
    """

    lock = RLock()

    def synchronized(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with lock:
                return func(*args, **kwargs)
        return wrapper

    class NuvoSync(Nuvo):
        def __init__(self, port_url):
            _LOGGER.info('Attempting connection - "%s"', port_url)
            self._port = serial.serial_for_url(port_url, do_not_open=True)
            self._port.baudrate = 57600
            self._port.stopbits = serial.STOPBITS_ONE
            self._port.bytesize = serial.EIGHTBITS
            self._port.parity = serial.PARITY_NONE
            self._port.timeout = TIMEOUT_OP
            self._port.write_timeout = TIMEOUT_OP
            self._port.open()


        def _send_request(self, request):
            """
            :param request: request that is sent to the nuvo
            :return: bool if transmit success
            """
            #format and send output command
            lineout = "*" + request + "\r"
            _LOGGER.debug('Sending "%s"', lineout)
            self._port.write(lineout.encode())
            self._port.flush() # it is buffering
            return True


        def _listen_maybewait(self, wait_for_response: bool):
            """
            :receives and parses data from nuvo until EOL or timeout
            :return: None
            """
            no_data = False
            receive_buffer = b'' 
            message = b''
            start_time = time.time()
            timeout = TIMEOUT_RESPONSE 

            # listen for response
            while (no_data == False):

               # Exit if timeout
               if( (time.time() - start_time) > timeout ):
 #                 _LOGGER.warning('Expected response from command but no response before timeout')
                  return None

               # fill buffer until we get term seperator 
               data = self._port.read(1)
               #_LOGGER.debug('Received data: %s', data)
               if data:
                  receive_buffer += data

                  if EOL in receive_buffer:
                     #_LOGGER.debug('Received buffer: %s', receive_buffer)
                     message, sep, receive_buffer = receive_buffer.partition(EOL)
                     _LOGGER.debug('Received: %s', message)
                     _parse_response(str(message))
                     return(str(message))
                  else:
                     pass
#                     _LOGGER.debug('Expecting response from command sent - Data received but no EOL yet...')

               else:

                  if ( wait_for_response == False ): 
                     no_data = True
#                     _LOGGER.debug('Expecting response from command sent - No Data received')
                  continue

            return None

        def _process_request(self, request: str):
            """
            :param request: request that is sent to the nuvo
            :return: ascii string returned by nuvo
            """

            # Process any messages that have already been received 
            self._listen_maybewait(False)

            # Send command to device
            self._send_request(request)

            # Process expected response
            rtn =  self._listen_maybewait(True)
            _LOGGER.debug('process maybewait return value: %s', rtn)
            return rtn

        @synchronized
        def zone_status(self, zone: int):
#            # Send command multiple times, since we need result back, and rarely response can be wrong type 
#            for count in range(1,2):
#               try:
#                  #_LOGGER.debug('zone_status string: %s', self._process_request(_format_zone_status_request(zone)))
#                  rtn = ZoneStatus.from_string(self._process_request(_format_zone_status_request(zone)))
#                  #_LOGGER.debug('zone_status rtn: %s', rtn)
#                  if rtn == None:
#                     _LOGGER.debug('Zone Status Request - Response Invalid - Retry Count: %d' , count)
#                     raise ValueError('Zone Status Request - Response Invalid')
#                  else:
#                     return rtn
#                     break  # Successful execution; exit for loop
#               except:
#                  rtn = None
#               #Wait 1 sec between retry attempt(s)
#               time.sleep(1)
#               continue  # end of for loop // retry
#            return rtn

            return ZoneStatus.from_string(self._process_request(_format_zone_status_request(zone)))

        @synchronized
        def set_power(self, zone: int, power: bool):
            self._process_request(_format_set_power(zone, power))

        @synchronized
        def set_mute(self, zone: int, mute: bool):
            self._process_request(_format_set_mute(zone, mute))

        @synchronized
        def set_volume(self, zone: int, volume: int):
            self._process_request(_format_set_volume(zone, volume))

        @synchronized
        def set_treble(self, zone: int, treble: float):
            self._process_request(_format_set_treble(zone, treble))

        @synchronized
        def set_bass(self, zone: int, bass: float):
            self._process_request(_format_set_bass(zone, bass))

        @synchronized
        def set_source(self, zone: int, source: int):
            self._process_request(_format_set_source(zone, source))

        @synchronized
        def restore_zone(self, status: ZoneStatus):
            self.set_power(status.zone, status.power)
            self.set_mute(status.zone, status.mute)
            self.set_volume(status.zone, status.volume)
            self.set_source(status.zone, status.source)
            self.set_treble(status.zone, status.treble)
            self.set_bass(status.zone, status.bass)

    return NuvoSync(port_url)
  
