# Synthesized Study Material

## Hash Functions and Digital Signatures

### Overview

This material combines lecture notes with practical examples of cryptographic hash functions and digital signatures.

### Hash Functions

#### Properties of Cryptographic Hash Functions

1. **Deterministic**: Same input always produces same output
2. **Fixed Output Size**: Regardless of input size
3. **Avalanche Effect**: Small input change causes large output change
4. **One-way Function**: Computationally infeasible to reverse
5. **Collision Resistant**: Hard to find two inputs with same hash

#### Common Hash Functions

| Algorithm | Output Size | Security Level | Status |
|-----------|-------------|----------------|--------|
| MD5 | 128 bits | Broken | Deprecated |
| SHA-1 | 160 bits | Weak | Deprecated |
| SHA-256 | 256 bits | Strong | Recommended |
| SHA-3 | Variable | Strong | Recommended |

### Digital Signatures

#### RSA Signature Process

1. **Key Generation**: Create public/private key pair
2. **Signing**: $S = M^d \bmod n$ (where $d$ is private key)
3. **Verification**: $M = S^e \bmod n$ (where $e$ is public key)

#### ECDSA (Elliptic Curve Digital Signature Algorithm)

```python
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

# Generate private key
private_key = ec.generate_private_key(ec.SECP256R1())
public_key = private_key.public_key()

# Sign message
message = b"Important document"
signature = private_key.sign(message, ec.ECDSA(hashes.SHA256()))

# Verify signature
try:
    public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
    print("Signature valid")
except:
    print("Signature invalid")
```

### Practice Problems

1. Calculate SHA-256 hash of your name
2. Implement simple digital signature verification
3. Compare performance of different hash algorithms