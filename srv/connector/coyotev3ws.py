import json, uuid, traceback, asyncio
from loguru import logger
import websockets
from websockets.legacy.protocol import WebSocketCommonProtocol

from srv import WS_CONNECTIONS, DEFAULT_WAVE #, WS_CONNECTIONS_ID_REVERSE, WS_BINDS

class DGWSMessage():
    HEARTBEAT = json.dumps({'type': 'heartbeat', 'clientId': '', 'targetId': '', 'message': '200'})
    def __init__(self, type, clientId="", targetId="", message="") -> None:
        self.type = type
        self.clientId = clientId
        self.targetId = targetId
        self.message = message
    
    def __str__(self) -> str:
        return json.dumps({
            'type': self.type,
            'clientId': self.clientId,
            'targetId': self.targetId,
            'message': str(self.message),
        })
    async def send(self, conn):
        msg = self.__str__()
        logger.debug(f'[ws] Device {conn.uuid} sending: {msg}')
        ret = await conn.ws_conn.send(msg)
        return ret

class DGConnection():
    wave_observer = None
    clear_observer = None
    _suppress_clear = False
    # Strong refs to fire-and-forget tasks so they are not GC'd mid-flight
    _pending_tasks = set()

    def __init__(self, ws_connection: WebSocketCommonProtocol, client_uuid=None, SETTINGS:dict=None) -> None:
        if SETTINGS is None:
            raise ValueError("DGConnection SETTINGS not provided.")
        self.ws_conn = ws_connection
        if client_uuid is None:
            client_uuid = ws_connection.id
        self.uuid = str(client_uuid)

        self.SETTINGS = SETTINGS
        self.master_uuid = SETTINGS['ws']['master_uuid']

        limit_a = SETTINGS['dglab3']['channel_a']['strength_limit']
        limit_b = SETTINGS['dglab3']['channel_b']['strength_limit']
        overlimit_a = SETTINGS['dglab3']['channel_a'].get('overlimit_max', 20)
        overlimit_b = SETTINGS['dglab3']['channel_b'].get('overlimit_max', 20)

        self.strength       = {'A':0, 'B':0}
        self.strength_max   = {'A':0, 'B':0}
        self.strength_limit = {'A':limit_a, 'B':limit_b}
        self.overlimit_max  = {'A':overlimit_a, 'B':overlimit_b}
        self.overlimit_active = {'A': False, 'B': False}

        WS_CONNECTIONS.add(self)
        # WS_CONNECTIONS_ID_REVERSE[self.uuid] = self
    
    def __str__(self):
        return f"<DGConnection (id:{self.uuid}, {self.strength}, max {self.strength_max})>"
    
    async def msg_handler(self, msg: DGWSMessage):
        if msg.type == 'bind':
            # APP send bind request.
            # Explicit checks, not assert: `python -O` strips assert statements,
            # which would turn this into an unauthenticated bind.
            if msg.targetId != self.uuid:
                logger.warning(f'[ws] Device {self.uuid} bind rejected: UUID mismatch ({msg.targetId})')
                return
            if msg.clientId != self.master_uuid:
                logger.warning(f'[ws] Device {self.uuid} bind rejected: unknown controller {msg.clientId}')
                return
            ret = DGWSMessage('bind', clientId=msg.clientId, targetId=msg.targetId, message='200')
            await ret.send(self)
        elif msg.type == 'msg':
            # 跟随强度变化
            if msg.message.startswith('strength-'):
                payload = msg.message[len('strength-'):].split('+')
                if len(payload) != 4:
                    logger.warning(f'[ws] Device {self.uuid} malformed strength msg: {msg.message}')
                    return
                try:
                    values = [int(v) for v in payload]
                except ValueError:
                    logger.warning(f'[ws] Device {self.uuid} malformed strength msg: {msg.message}')
                    return
                self.strength['A'], self.strength['B'], self.strength_max['A'], self.strength_max['B'] = values
                for chann in ['A', 'B']:
                    limit = self.get_upper_strength(chann)
                    if (self.strength[chann] != 0 and self.strength[chann] != limit):
                        await self.set_strength(chann, value=limit)
            elif msg.message.startswith('feedback-'):
                logger.info(f'[ws] Device {self.uuid} feedback: {msg.message}')
            else:
                logger.warning(f'[ws] Device {self.uuid} unknown msg: {msg.message}')
        elif msg.type == 'heartbeat':
            logger.debug(f'[ws] Device {self.uuid} heartbeat')
    
    def get_upper_strength(self, channel='A'):
        limit = self.strength_limit[channel]
        if self.overlimit_active[channel]:
            # overlimit_max is an absolute cap set by rules, not additive
            limit = max(limit, self.overlimit_max[channel])
        return min(self.strength_max[channel], limit)

    async def set_strength(self, channel='A', mode='2', value=0, force=False):
        if not force:
            if value < 0 or value > 200:
                raise ValueError()
            limit = self.get_upper_strength(channel)
            if value > int(limit) and mode == '2':
                logger.warning(f'[ws] Device {self.uuid} set_strength: {value} over limit {limit}, clamping to {limit}')
                value = limit
        if mode == '2':
            self.strength[channel] = value
        logger.debug(f'[ws] Set strength: ch={channel} mode={mode} val={value}')
        msg = DGWSMessage('msg', self.master_uuid, self.uuid, f"strength-{'1' if channel == 'A' else '2'}+{mode}+{value}")
        await msg.send(self)

    async def set_strength_0_to_1(self, channel='A', value=0):
        if value < 0 or value > 1:
            raise ValueError()
        limit = self.get_upper_strength(channel)
        strength = int(limit * value)
        await self.set_strength(channel=channel, mode='2', value=strength)

    async def send_wave(self, channel='A', wavestr=DEFAULT_WAVE):
        msg = DGWSMessage('msg', self.master_uuid, self.uuid, f"pulse-{channel}:{wavestr}")
        await msg.send(self)
    
    async def clear_wave(self, channel='A'):
        channel = '1' if channel == 'A' else '2'
        msg = DGWSMessage('msg', self.master_uuid, self.uuid, f"clear-{channel}")
        await msg.send(self)
    
    async def send_err(self, type=''):
        msg = DGWSMessage(type, )
    
    async def heartbeat(self):
        while 1:
            await asyncio.sleep(60)
            logger.debug(f'[ws] Device {self.uuid} sending heartbeat')
            await self.ws_conn.send(DGWSMessage.HEARTBEAT)
    
    async def connection_init(self):
        await asyncio.sleep(2)
        await self.set_strength('A', value=1, force=True)
        await self.set_strength('B', value=1, force=True)

    async def serve(self):
        logger.success(f'[ws] Device connected: {self.uuid}')
        msg = DGWSMessage('bind', clientId=str(self.uuid), targetId='', message='targetId')
        await msg.send(self)
        init = asyncio.ensure_future(self.connection_init())
        hb = asyncio.ensure_future(self.heartbeat())
        try:
            async for message in self.ws_conn:
                logger.debug(f'[ws] Device {self.uuid} recv: {message}')
                try:
                    event = json.loads(message)
                    msg = DGWSMessage(**event)
                except (ValueError, TypeError) as exc:
                    logger.warning(f'[ws] Device {self.uuid} malformed message: {exc!r}')
                    continue
                try:
                    await self.msg_handler(msg)
                except Exception:
                    logger.error(f'[ws] {traceback.format_exc()}')
            await self.ws_conn.wait_closed()
        finally:
            logger.warning(f'[ws] Device disconnected: {self.uuid}')
            # connection_init sleeps 2s before writing; leaving it running would
            # make it write to an already closed socket.
            for task in (hb, init):
                task.cancel()
            await asyncio.gather(hb, init, return_exceptions=True)
            # discard, not remove: the connection may already be gone
            WS_CONNECTIONS.discard(self)

    @staticmethod
    async def _fanout(action, what):
        """Run `action` against a snapshot of all connections, tolerating failures.

        Iterating WS_CONNECTIONS directly while awaiting is unsafe: a device
        disconnecting mid-broadcast mutates the set ("Set changed size during
        iteration"), and one dead socket used to abort the whole broadcast and
        propagate the exception up into the wave feeder, killing it.
        """
        conns = list(WS_CONNECTIONS)
        if not conns:
            return
        results = await asyncio.gather(
            *(action(conn) for conn in conns), return_exceptions=True
        )
        for conn, result in zip(conns, results):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, BaseException):
                logger.warning(f'[ws] Device {conn.uuid} {what} failed: {result!r}')

    @classmethod
    async def broadcast_wave(cls, channel='A', wavestr=DEFAULT_WAVE):
        if cls.wave_observer is not None:
            try:
                cls.wave_observer(channel, wavestr)
            except Exception:
                logger.exception('[ws] wave_observer failed')
        await cls._fanout(
            lambda conn: conn.send_wave(channel=channel, wavestr=wavestr), 'send_wave'
        )

    @classmethod
    async def broadcast_clear_wave(cls, channel='A'):
        if cls._suppress_clear:
            return
        if cls.clear_observer is not None:
            try:
                cls.clear_observer(channel)
            except Exception:
                logger.exception('[ws] clear_observer failed')
        await cls._fanout(lambda conn: conn.clear_wave(channel=channel), 'clear_wave')

    @classmethod
    async def broadcast_strength_0_to_1(cls, channel='A', value=0):
        await cls._fanout(
            lambda conn: conn.set_strength_0_to_1(channel=channel, value=value),
            'set_strength_0_to_1',
        )

    @classmethod
    def refresh_limits_from_settings(cls, settings: dict):
        limit_a = settings['dglab3']['channel_a']['strength_limit']
        limit_b = settings['dglab3']['channel_b']['strength_limit']
        overlimit_a = settings['dglab3']['channel_a'].get('overlimit_max', 20)
        overlimit_b = settings['dglab3']['channel_b'].get('overlimit_max', 20)
        for conn in list(WS_CONNECTIONS):
            conn: cls
            conn.strength_limit['A'] = limit_a
            conn.strength_limit['B'] = limit_b
            conn.overlimit_max['A'] = overlimit_a
            conn.overlimit_max['B'] = overlimit_b
        # Push new limits to devices immediately
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # No event loop running (e.g. during init)
        task = loop.create_task(cls._apply_limits_to_devices())
        # Keep a reference so the task is not garbage collected mid-flight,
        # and surface failures instead of swallowing them.
        cls._pending_tasks.add(task)
        task.add_done_callback(cls._pending_tasks.discard)

    @classmethod
    async def _apply_limits_to_devices(cls):
        """Push current strength limits to all connected devices."""
        for conn in list(WS_CONNECTIONS):
            conn: cls
            for ch in ['A', 'B']:
                limit = conn.get_upper_strength(ch)
                # Only push if device is connected (strength_max > 0) and not manually zeroed
                if conn.strength_max[ch] > 0 and conn.strength[ch] != 0:
                    try:
                        await conn.set_strength(ch, mode='2', value=limit, force=True)
                    except Exception as exc:
                        logger.warning(f'[ws] Device {conn.uuid} limit push failed: {exc!r}')

    @classmethod
    async def broadcast_strength_adjust(cls, channel='A', mode='1', value=0):
        """Broadcast strength adjustment. mode: 0=sub, 1=add, 2=set.

        Additions stay subject to the configured strength limit: boost mode used
        to pass force=True here, which skipped both the 0..200 range check and
        the strength_limit clamp, letting output exceed the user's cap.
        Subtraction is always allowed through.
        """
        async def apply(conn):
            effective = value
            if mode == '1':
                limit = conn.get_upper_strength(channel)
                headroom = max(0, int(limit) - conn.strength[channel])
                effective = min(value, headroom)
                if effective != value:
                    logger.warning(
                        f'[ws] Device {conn.uuid} ch={channel} boost +{value} exceeds '
                        f'limit {limit} (current {conn.strength[channel]}), capped to +{effective}'
                    )
                if effective <= 0:
                    return
                conn.strength[channel] = conn.strength[channel] + effective
            elif mode == '0':
                effective = min(value, conn.strength[channel])
                if effective <= 0:
                    return
                conn.strength[channel] = conn.strength[channel] - effective
            await conn.set_strength(channel, mode=mode, value=effective, force=True)

        await cls._fanout(apply, f'strength_adjust(mode={mode})')

    @classmethod
    def set_overlimit(cls, channel='A', active=True):
        """Enable or disable overlimit for a channel across all connections."""
        for conn in list(WS_CONNECTIONS):
            conn: cls
            conn.overlimit_active[channel] = active
