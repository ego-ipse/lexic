from with_guidance import approach_a_guidance, approach_b_raw
import signal

# Run A with timeout
def handler(s, f): raise TimeoutError()
signal.signal(signal.SIGALRM, handler)

signal.alarm(15)
try:
    result_a = approach_a_guidance('/home/mika/SmolLM2.q8.gguf', 'test: ')
    print('A result:', repr(result_a))
except TimeoutError:
    print('A timed out (hangs)')
except Exception as e:
    print('A error:', e)
finally:
    signal.alarm(0)

# Now run B
print('Running B...')
signal.alarm(15)
try:
    result_b = approach_b_raw('/home/mika/SmolLM2.q8.gguf', 'test: ')
    print('B result:', repr(result_b))
except TimeoutError:
    print('B timed out')
except Exception as e:
    print('B error:', e)
finally:
    signal.alarm(0)
