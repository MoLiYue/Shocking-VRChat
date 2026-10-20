from loguru import logger
import asyncio
import math

class BaseHandler():
    
    @staticmethod
    def param_sanitizer(param):
        try:
            param = param[0]
        except:
            pass
        # bool must be checked before int: bool is a subclass of int
        if isinstance(param, bool):
            param = 1 if param else 0
        elif isinstance(param, float):
            # min/max do not filter NaN: max(nan, 0.0) returns nan, which would
            # propagate all the way into strength calculation. A malformed
            # value must fail safe to 0, never to max strength.
            if not math.isfinite(param):
                logger.warning(f'[handler] Non-finite OSC param {param!r}, treated as 0')
                param = 0.0
            else:
                param = min(max(param, 0.0), 1.0)
        elif isinstance(param, int):
            param = min(max(param, 0), 1)
        else:
            raise ValueError('错误的输入参数类型，仅支持 1~0 之间的 float、int 或 bool。')
        return param

    def osc_handler(self, address, *args):
        # logger.debug(f"VRCOSC: CHANN {self.channel}: {address}: {args}")
        val = self.param_sanitizer(args)
        context = {
            'address': address,
            'raw_args': list(args),
            'sanitized_value': val,
        }
        asyncio.ensure_future(self._handler(val, context=context))
        return None
