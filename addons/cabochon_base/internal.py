"""Process-local capabilities. RPC JSON values cannot impersonate these objects."""

INTERNAL = object()


def is_internal(env, key):
    return env.context.get(key) is INTERNAL
