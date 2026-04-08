# La realidad de los small miners — análisis definitivo

Este archivo reemplaza y corrige los análisis previos en `findings.md` y
`refined_proposal.md`. Contiene la conclusión honesta después de
iterar sobre varios modelos equivocados.

---

## 1. La composición real de la red (datos de VPS1 RPC, E50)

**29 productores activos, 1,891 bonos totales:**

| Grupo | Productores | Bonos/productor | Total bonds | % de red |
|---|---|---|---|---|
| **Structural** (team tier 1) | 6 | 276 (simetría perfecta) | 1,656 | **87.6%** |
| **Mid-miners** (team tier 2) | 6 | 27 (simetría perfecta) | 162 | 8.6% |
| **Small miners** (orgánicos) | 17 | 1–10 (variables) | 73 | **3.9%** |

La simetría perfecta de los dos primeros grupos (exactamente 276 y
exactamente 27) es evidencia contundente de coordinación: el equipo
controla **12 productores** (96.1% de la red), no 6. La "comunidad"
orgánica son los 17 productores pequeños con 73 bonos combinados.

### Distribución de los 17 small miners
| Bonos | Cantidad | Probablemente entraron cuando B era… |
|---|---|---|
| 10 | 1 | muy temprano (B < 600) |
| 7 | 1 | temprano (B ~700) |
| 6 | 2 | E25-E28 |
| 5 | 5 | E28-E35 |
| 4 | 2 | E35-E40 |
| 3 | 1 | reciente |
| 2 | 3 | muy reciente |
| **1** | **2** | **recién llegados** |

---

## 2. El whitepaper sobre bootstrap (Sección 16.2)

El whitepaper describe un proceso de 3 fases en el primer epoch:

- **Phase 1:** Cinco genesis producers con placeholder (sin valor)
- **Phase 2:** En block 361, el protocolo crea 1 bond real (10 DOLI) por cada genesis producer
- **Phase 3:** Desde block 361, reglas iguales para todos

El whitepaper también admite (línea 1046):
> *"The chain has undergone multiple genesis resets during bootstrap; metrics below reflect the current chain (genesis: 2026-03-19)."*

Así que los 6 structural actuales no siguen necesariamente el
procedimiento del whitepaper al pie de la letra. Pero el head start
económico es real: cuando `B` era muy pequeño, los structural
compusieron rápido, dejando atrás a cualquiera que entrara después.

---

## 3. La fórmula del techo aplicada a la realidad

Para cualquier productor con `b` bonos bajo dilución `d`, el lifetime
cumulative reward es una serie geométrica convergente:

```
lifetime_reward(b) = b · s / d = b · (360/B) / d
```

Si `lifetime_reward < BOND_UNIT (10 DOLI)`, el productor **nunca más
bondea**.

Despejando para el límite inferior de viabilidad:

```
s > 10 · d / b
B < 36 · b / d
```

### Condiciones de viabilidad para bondear UNA vez más

Con `d = 0.03` (observado actualmente):

| Bonos `b` | B máximo para bondear uno más | Estado actual (B=1891) |
|---|---|---|
| 1 | 1,200 | **WALL. Imposible.** |
| 2 | 2,400 | Viable por ~14 epochs más |
| 3 | 3,600 | ~48 epochs más |
| 4 | 4,800 | ~80 epochs más |
| 5 | 6,000 | ~113 epochs más (~5 días) |
| 7 | 8,400 | ~180 epochs más |
| 10 | 12,000 | ~280 epochs más (~12 días) |

**Todos los small miners actuales tienen su muro absoluto a días o
semanas de distancia. Los 2 con 1 bono ya están walled.**

---

## 4. Simulación definitiva: 1-bond miner entrando hoy

Simulamos un productor nuevo de 1 bono iniciando en E50 (estado actual),
bajo dilución del 3% por época, durante toda Era 1 (35,040 epochs ≈ 4
años).

**Resultado:**

```
E   150 (día 4):    b=1  spendable=5.88  ← plateau inminente
E   550 (día 21):   b=1  spendable=6.18  ← plateau alcanzado
E  1050 (día 42):   b=1  spendable=6.18  ← no sube más
E 35090 (4 años):   b=1  spendable=6.18  ← NEVER BONDED
```

**Cero bonos añadidos. El miner no bondea nunca en toda Era 1.**

Cálculo analítico:
```
lifetime = 1 × 0.1904 / 0.0299 = 6.37 DOLI
```

Es **todo lo que puede ganar en toda la vida del protocolo**. 6.37 < 10.
**Imposible bondear.**

Incluso en un escenario optimista donde `d` decae linealmente de 3% a
0.1% durante Era 1, el resultado es el mismo: plateau a ~6.16 DOLI, cero
bonos, never bonded.

---

## 5. La declaración del whitepaper es matemáticamente imposible

El whitepaper, Sección 10.8:

> *"Starting with 10 DOLI, a producer who reinvests all rewards reaches
> the 3,000-bond cap within months."*

**Bajo las condiciones reales de la red, esto es imposible.**

El ejemplo numérico del whitepaper asume `B = 18,000` constante. Esa
suposición no corresponde a la realidad: `B` crece mientras el productor
compounde, y la dilución compuesta mata su progreso antes del primer
bond adicional.

La promesa del whitepaper solo es válida si:
1. La red se mantiene a `B ≈ 18,000` indefinidamente (no ocurre)
2. Todos los productores están en lockstep perfecto (no ocurre)
3. No hay nuevos entrantes más allá del productor del ejemplo (no ocurre)

Ninguna de esas tres condiciones se cumple en la red real. Por lo tanto,
la promesa no es alcanzable por ningún productor nuevo.

---

## 6. Cronología real de la muerte de la comunidad

Asumiendo que B sigue creciendo al ritmo actual (~36 bonos/epoch):

| Tipo de small miner | Epoch en que toca su muro | Tiempo desde E50 |
|---|---|---|
| Miners de 1 bond (2 productores) | Ya están walled | 0 |
| Miners de 2 bonds (3 productores) | E~64 | ~14 horas |
| Miners de 3 bonds (1 productor) | E~98 | ~2 días |
| Miners de 4 bonds (2 productores) | E~130 | ~3.5 días |
| Miners de 5 bonds (5 productores) | E~163 | ~4.7 días |
| Miners de 6 bonds (2 productores) | E~196 | ~6 días |
| Miners de 7 bonds (1 productor) | E~230 | ~7.5 días |
| Miners de 10 bonds (1 productor) | E~330 | ~12 días |

**Cronología resumida: la comunidad entera muere en 2 semanas.**

Los structural nodes se saturan a E566 (~21 días). Pero para entonces,
**todos los small miners ya están walled**. La "saturación estructural
que libera el techo" no sucede a tiempo.

---

## 7. La suma total del techo de la comunidad

Los 17 small miners combinados pueden añadir como mucho **~68 bonos
adicionales** sumando todos sus techos individuales. Después de eso, la
comunidad queda congelada.

- Ahora: 17 productores, 73 bonos, 3.9% de la red
- En 2 semanas: 17 productores, ~141 bonos, **~0.76% de una red que
  tiene 18,000+ bonos del equipo**

La descentralización medida por bonos comunitarios **colapsa de 3.9% a
<1% en dos semanas**. Los productores existen pero son insignificantes.

---

## 8. Conclusión

**El modelo actual de DOLI es, en la práctica, una red controlada al
96.1% por el equipo, con una comunidad orgánica que muere
matemáticamente en los primeros 14 días del primer mes de Era 1.**

No es un problema de "largo plazo". No es un problema de "Era 2 cuando
haya halving". Es un problema de **esta semana**.

La única forma de que la comunidad sobreviva bajo el modelo actual es:

1. **Que el equipo rechace esta conclusión** — necesitarían mostrar un
   error en las fórmulas. Las fórmulas son del propio whitepaper.
2. **Que la dilución caiga dramáticamente** — requiere que los
   structural dejen de compoundear. No hay mecanismo que los obligue.
3. **Que los small miners compren DOLI en mercado secundario** — la
   solución oficial del equipo, pero convierte DOLI en un sistema
   dependiente de capital externo, contradiciendo el pitch del whitepaper.
4. **Delegación** — existe en el código (`bins/node/src/node/rewards.rs:238-278`)
   y permite a un small holder delegar bonds a un productor grande
   (90/10 split). No rompe la matemática del techo (los rewards siguen
   siendo bond-weighted), pero ahorra el costo operativo del VPS. Es
   la solución implícita del equipo en el código, aunque no está en el
   whitepaper. Efectivamente, convierte la "red descentralizada" en
   una de productores estructurales con delegadores pasivos — el
   opuesto del pitch original.
5. **Cambio de protocolo** — BOND_UNIT elástico, doubling rewards,
   demurrage, o alguna combinación.

Las opciones 1-4 no son soluciones reales. La 5 es la única salida
honesta.
