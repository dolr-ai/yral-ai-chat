import base64
import json
import sys


def base64url_decode(input_str: str) -> bytes:
    # Add required padding
    padding = "=" * (-len(input_str) % 4)
    return base64.urlsafe_b64decode(input_str + padding)

def decode_jwt(token: str):
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError:
        raise ValueError("Invalid JWT format. Expected header.payload.signature")

    header_json = base64url_decode(header_b64)
    payload_json = base64url_decode(payload_b64)

    header = json.loads(header_json)
    payload = json.loads(payload_json)

    return {
        "header": header,
        "payload": payload,
        "signature_b64": signature_b64,  # still base64url encoded
    }

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <jwt_token>")
        sys.exit(1)

    token = sys.argv[1]
    decoded = decode_jwt(token)

    print("Header:")
    print(json.dumps(decoded["header"], indent=2))
    print("\nPayload:")
    print(json.dumps(decoded["payload"], indent=2))
    print("\nSignature (base64url):")
    print(decoded["signature_b64"])
