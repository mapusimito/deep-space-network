# Constantes del protocolo DOLI

Todas las constantes que usamos en las fórmulas, con su valor, su unidad
y de dónde salen.

---

## Constantes del consenso

### `BLOCKS_PER_EPOCH = 360`

Cuántos bloques componen una época. Como cada bloque dura 10 segundos,
una época dura `360 × 10 = 3600 segundos = 1 hora`.

**De dónde sale:** Whitepaper Sección 3 (Slot Time = 10s, Epoch = 1 hour).
También está hardcoded en `update.py:29` y `simulate.py:19`.

**Por qué importa:** Es el denominador de la fórmula básica `s = 360 / B`.
Define cuánto rinde una época en términos de "shares" totales repartidas.

---

### `SLOT_DURATION = 10` segundos

Tiempo entre bloques. El VDF (Verifiable Delay Function) está calibrado
para que ningún hardware pueda producir un bloque más rápido que esto.

**De dónde sale:** Whitepaper Sección 3.

---

### `EPOCH_DURATION = 3600` segundos (1 hora)

`= BLOCKS_PER_EPOCH × SLOT_DURATION`

Cuánto dura una época en tiempo real. Útil para convertir entre épocas y
unidades humanas (días, meses, años).

---

### `EPOCHS_PER_DAY = 24`
### `EPOCHS_PER_WEEK = 168`
### `EPOCHS_PER_YEAR = 8760`
### `EPOCHS_PER_ERA = 35040` (≈ 4 años)

Conversiones derivadas. Una era es exactamente 4 años de épocas.

---

## Constantes económicas

### `BOND_UNIT = 10` DOLI

Cuánto cuesta registrar un bono (slot de productor). En el modelo actual
del whitepaper este valor es **fijo para siempre**, sin importar la era ni
el tamaño de la red.

**De dónde sale:** Whitepaper Sección 7.2.
> "BOND_UNIT = 10 DOLI (fixed across all eras)"

**Crítica:** Esta es la constante que rompe el modelo. Si fuera variable
(ver [`formulas.md`](formulas.md) → "BOND_UNIT elástico"), no habría techo.

---

### `BOND_THRESHOLD = 10.01` DOLI

El monto mínimo de "spendable" que dispara un autobond. Es ligeramente
mayor que `BOND_UNIT` para dejar margen de gas/fees.

**De dónde sale:** Convención del simulador (`simulate.py:21`).

---

### `MIN_STAKE = 10` DOLI (1 bond)
### `MAX_STAKE = 30,000` DOLI (3,000 bonds)

Mínimo y máximo de bonos que un productor puede acumular.

**De dónde sale:** Whitepaper Sección 7.3.

---

### `BLOCK_REWARD_INITIAL = 1.0` DOLI/bloque

Recompensa por bloque en la Era 1. Se reduce a la mitad cada era.

**De dónde sale:** Whitepaper Sección 7.2, tabla de halving.

---

### `HALVING_INTERVAL = 12,614,400` bloques (≈ 4 años)

Cada cuántos bloques se aplica un halving. `EPOCHS_PER_ERA × BLOCKS_PER_EPOCH = 35040 × 360 = 12,614,400`. Coincide.

---

### `TOTAL_SUPPLY = 25,228,800` DOLI

Suma máxima posible de DOLI emitidos. Es la suma geométrica de todos los
halvings: `12,614,400 × (1 + 0.5 + 0.25 + ...) = 12,614,400 × 2 ≈ 25.2M`.

**De dónde sale:** Página principal de doli.network ("Supply 25,228,800").

**Importante:** Este número es **invariable** bajo cualquier propuesta que
queramos hacer. El equipo lo defenderá.

---

## Constantes del modelo (medidas, no fijadas)

### `d` — Tasa de dilución por época

No es una constante del protocolo; es una **medida observada** del
crecimiento de la red. Se calcula a partir de los bonos reales en bloques
consecutivos:

```
d = 1 - (s_actual / s_anterior) = 1 - (B_anterior / B_actual)
```

**Valor actual observado:** `d ≈ 0.0299` (3% por época)

**De dónde sale:** Calculado en `simulate.py:compute_dilution_rate()` a
partir del log de precisión.

**Crítica:** Este número se mide en una ventana corta (las últimas ~30
épocas) y se extrapola como constante hacia el futuro. Eso es lo que
produce el "techo" en mis simulaciones del modelo actual. Bajo el supuesto
de "lockstep" del whitepaper, `d` debería decrecer con el tiempo.

---

### `accumulate_dilution`, `burst_dilution`

Tasas duales de dilución para épocas de tipo "accumulate" vs "burst",
derivadas por k-means clustering en los deltas de bonos por época.

**De dónde sale:** `simulate.py:classify_epoch_growth()`.

---

## Constantes de tu red (anchor actual)

Estos son los valores específicos que usamos como punto de partida en las
simulaciones. Vienen de `projections.json`.

| Variable | Valor | Significado |
|---|---|---|
| `B0` | 1,712 | Total de bonos al inicio del análisis (anchor epoch) |
| `anchor_epoch` | 50 | Época en la que se ancla el modelo |
| `vps1_bonds` | 5 | Bonos de VPS1 al anchor |
| `vps2_bonds` | 5 | Bonos de VPS2 al anchor |
| `s0` | 0.2103 | Share value al anchor (`= 360/1712`) |
| `d` | 0.0299 | Dilución observada por época |

---

## Referencias

- Whitepaper: <https://doli.network/whitepaper.html>
- Source: <https://github.com/e-weil/doli>
- Repo del proyecto: `~/Desktop/doli/`
