"""Approved synth payloads and the size-based portable release policy."""
APPROVED_PACKS=('stk-essentials','stk-colors','stk-acoustic')

def bundle_synths(core_bytes,synth_bytes):
    """Compare unpacked bytes on both sides, including source and licenses."""
    return core_bytes>0 and synth_bytes<=core_bytes
