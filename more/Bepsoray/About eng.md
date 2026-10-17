# Bepsoray

**Bepsoray** (formerly *Bepsolray*) is a one-way interstellar communication protocol
for transmitting data between star systems separated by more than one light-year.

The name combines three roots: **Bep** (beep — a sound pulse), **Sol** (the Sun,
a star), **Ray** (a beam of light). Together — "a stellar beep-ray": data sent
across the void as timed flashes.

---

## Core idea

Information is encoded **not in the presence of a flash**, but in the **interval
between flashes**, plus three additional degrees of freedom:

| Dimension | Range | Bits per symbol |
|-----------|-------|-----------------|
| Position (slot index) | M = 1024 | 10 |
| Pulse duration | 2 levels | 1 |
| Pulse intensity | 4 levels | 2 |
| Pulse shape | 2 levels | 1 |
| **Total** | | **14 bits / symbol** |

This is the **HPPM-4D** modulation scheme (High-Order Pulse-Position Modulation,
4 Dimensions). It extends classical PPM — the standard approach in deep-space
optical links — by using every physically controllable parameter of a pulse.

---

## Key principles

1. **One-way only.** No acknowledgement channel. Distances above one light-year
   make duplex impossible in practice; Bepsoray accepts this and compensates
   with strong forward error correction, preambles, and beacon mode.
2. **Asymmetry of cost.** A powerful transmitter with precise pointing makes the
   receiver's job simple. The harder the sender works, the cheaper the receiver.
3. **Distributed sources.** Multiple emitters (e.g. on orbits of different planets
   in one system) can transmit in parallel, increasing total aperture and
   throughput. Each source carries a unique ID and its own proper time.
4. **Relativistic honesty.** Every frame carries the transmitter's proper time
   (TAI64, nanosecond precision). The receiver, knowing ephemerides of the sender,
   applies corrections for Doppler shift and gravitational redshift — all
   without a return channel.

---

## Protocol stack

- **Layer 0 — Physical.** Pulsed laser, 1550 nm nominal; single-photon detectors
  on the receiving side.
- **Layer 1 — Modulation.** HPPM-4D, 14 bits per pulse, slot width 400 ps.
- **Layer 2 — Channel coding.** SCPPM (inner) + Reed–Solomon (255, 223) (outer),
  with interleaving.
- **Layer 3 — Framing.** Fixed frame: preamble (primes), sync marker (digits of pi),
  header (32 bits), payload (up to 917 kbit), CRC-32.
- **Layer 4 — Network.** Beacon / Data / Silence modes; optional spatial
  multiplexing across distributed emitters.
- **Layer 5 — Relativistic correction.** Proper-time stamps and ephemeris-based
  arrival-time prediction.

---

## Link budget (baseline)

For R = 1 light-year, 1550 nm, P_t = 100 kW, D_t = D_r = 10 m:

- Geometric capture factor: about 4.6e-17
- Received power: about 2.1e-12 W
- Photon rate: about 1.6e7 photons/s
- Achievable throughput: 16–160 Mbit/s depending on coding efficiency
  (1 to 10 bits per photon)

The scaling law is: **rate ∝ P_t · D_t² · D_r² / R²**.
Doubling the telescope diameter gives a 4x gain; doubling the power gives 2x.

---

## Status

Bepsoray v1.0 is a **conceptual protocol specification**. It is original in its
combination of HPPM-4D modulation, one-way framing with relativistic time stamps,
and distributed-source multiplexing under a single standard. Individual
components (PPM, Reed–Solomon, SCPPM) are known; their integration into a
one-way interstellar standard is the contribution.

See `Specifications/` for the full technical description.

---

*Maintained by Bizonrelax · Repository: Sigmawillow*
