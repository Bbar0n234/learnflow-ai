# Recognized Handwritten Notes

## Network Security Lecture

### SSL/TLS Protocol

- Transport Layer Security ensures secure communication
- Handshake Process:
  1. Client Hello → Server Hello
  2. Certificate exchange
  3. Key exchange (RSA or ECDH)
  4. Finished messages

### Perfect Forward Secrecy

> Even if long-term keys are compromised, past communications remain secure

**Achieved through:**
- Ephemeral key exchange (DHE, ECDHE)
- Session keys derived from temporary values
- Keys destroyed after use