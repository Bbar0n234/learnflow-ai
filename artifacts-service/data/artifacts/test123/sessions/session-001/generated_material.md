# Test Generated Material

This is a sample generated educational material.

## Cryptography Basics

### Symmetric Encryption

Symmetric encryption uses the same key for both encryption and decryption.

**Key Properties:**
- Fast encryption/decryption
- Requires secure key exchange
- Examples: AES, DES, 3DES

### Mathematical Formula

For AES encryption:
$$C = E_k(P)$$

Where:
- $C$ is ciphertext
- $P$ is plaintext
- $k$ is the secret key
- $E$ is the encryption function

## Code Example

```python
from cryptography.fernet import Fernet

# Generate a key
key = Fernet.generate_key()
cipher = Fernet(key)

# Encrypt data
plaintext = b"Secret message"
ciphertext = cipher.encrypt(plaintext)

# Decrypt data
decrypted = cipher.decrypt(ciphertext)
print(decrypted.decode())
```

## Summary

Symmetric encryption is fundamental to modern cryptography and forms the basis for many secure communication protocols.