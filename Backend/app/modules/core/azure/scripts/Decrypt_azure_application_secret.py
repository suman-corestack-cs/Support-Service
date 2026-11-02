import base64
from itertools import chain, zip_longest

from Crypto.Cipher import AES
from Crypto.Util import Padding


class PrivateState:
    """CoreStack's field encryption, exactly as used to store
    service_account_details.credentials.application_secret: "zzz1:"-prefixed
    values are AES-CBC (IV prepended), anything else is the legacy AES-ECB
    format padded with '{'."""

    TEXT_ENCODING = "utf-8"
    HEADER_V2 = "zzz1:"

    def __init__(self, seed):
        s = zip_longest(seed, seed[::-1], fillvalue="")
        s = "".join(chain.from_iterable(s))[0:AES.block_size][::-1]
        self._input = s.encode(PrivateState.TEXT_ENCODING)

    def decrypt(self, payload):
        if not payload:
            return ""
        if payload.startswith(PrivateState.HEADER_V2):
            return self._decrypt_v2(payload[len(PrivateState.HEADER_V2):])
        return self._decrypt_legacy(payload)

    def _decrypt_v2(self, payload):
        payload_bytes = base64.b64decode(payload)
        iv = payload_bytes[0:AES.block_size]
        full_ciphertext = payload_bytes[AES.block_size:]
        cipher = AES.new(self._input, AES.MODE_CBC, iv=iv)
        c = cipher.decrypt(full_ciphertext)
        return Padding.unpad(c, AES.block_size).decode(PrivateState.TEXT_ENCODING)

    def _decrypt_legacy(self, payload):
        payload_bytes = base64.b64decode(payload)
        cipher = AES.new(self._input, AES.MODE_ECB)
        return cipher.decrypt(payload_bytes).decode(PrivateState.TEXT_ENCODING).rstrip("{")


def decrypt_application_secret(encrypted_secret, seed):
    try:
        if not seed:
            return {"error": "CORESTACK_SECRET_DECRYPT_SEED is not set in Backend/.env — add it to decrypt secrets."}
        if not encrypted_secret:
            return {"error": "This cloud account has no stored application secret to decrypt."}

        decrypted = PrivateState(seed).decrypt(encrypted_secret)
        if not decrypted:
            return {"error": "Could not decrypt the application secret — it may not be in a recognized CoreStack encrypted format."}
        return {"application_secret": decrypted}
    except Exception as e:
        return {"error": f"Could not decrypt the application secret: {e}"}
