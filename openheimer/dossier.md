# Dossier — DOLI Economic Model: Ceiling Analysis for Small Producers

**Preparado por:** Análisis derivado del propio whitepaper y datos de la red
**Fecha:** 2026-04-08
**Chain:** Current chain (genesis 2026-03-19), E50 snapshot
**Referencias:** Whitepaper Secciones 7.2, 7.3, 10.2, 10.8, 16.2

---

## Resumen ejecutivo

La combinación de (a) `BOND_UNIT` fijo en 10 DOLI, (b) distribución de
rewards proporcional a bonos, y (c) halving programado produce una
trampa matemática para productores pequeños que **no está documentada en
el whitepaper** y que **contradice explícitamente** la promesa hecha en
la Sección 10.8.

Bajo las condiciones actuales de la red, un productor nuevo que entre
con 10 DOLI (1 bond) enfrenta un techo de ganancias de por vida
**inferior al costo de un solo bond adicional**. No puede bondear nunca
más, independientemente de cuánto tiempo espere.

Este documento presenta las fórmulas, los datos de la red, y los
resultados de las simulaciones que soportan esta conclusión.

---

## 1. Declaraciones del whitepaper evaluadas

### 1.1 Declaración central (Sección 10.8)

> *"Starting with 10 DOLI, a producer who reinvests all rewards reaches
> the 3,000-bond cap within months."*

**Estado:** Matemáticamente imposible bajo las condiciones reales de la red.

### 1.2 Afirmación de auto-regulación (Sección 10.8)

> *"Self-regulation: As B grows, D increases proportionally. Rapid early
> growth naturally converges toward stable distribution without
> governance intervention."*

**Estado:** No está respaldada por ningún mecanismo del protocolo. Es
una afirmación sin prueba ni mecanismo enforce. Empíricamente, la
dilución observada no ha convergido; se mantiene alrededor del 2-3% por
época.

### 1.3 Afirmación de independencia del bond count

> *"D is independent of b. A producer with 1 bond and a producer with
> 1,000 bonds both double their stake in D weeks."*

**Estado:** Matemáticamente cierto en un instante dado, pero engañoso
sobre múltiples épocas porque `D` crece con `B`, y `B` crece
continuamente. El "independiente de `b`" omite la dependencia de `B(t)`.

---

## 2. Estado real de la red (datos RPC, E50)

**Fuente:** `getProducers(active_only=true)` en VPS1 (187.124.148.105)

### 2.1 Distribución de productores

**Total:** 29 productores, 1,891 bonos

| Grupo | N | Bonds c/u | Total | % red |
|---|---|---|---|---|
| Tier 1 (structural) | 6 | 276 | 1,656 | 87.6% |
| Tier 2 (mid-miners) | 6 | 27 | 162 | 8.6% |
| Tier 3 (small miners) | 17 | 1–10 | 73 | 3.9% |

### 2.2 Observación crítica: simetría perfecta en tiers 1 y 2

Los 6 productores del Tier 1 tienen **exactamente 276 bonos** cada uno.
Los 6 del Tier 2 tienen **exactamente 27** cada uno. Esta simetría es
estadísticamente imposible en una distribución orgánica. Indica
coordinación — 12 productores controlados por una sola entidad.

**Implicación:** el equipo controla **96.1%** de los bonos de la red,
no 87.6%.

### 2.3 Composición de los 17 small miners (tier 3)

| Bonos | Productores |
|---|---|
| 10 | 1 |
| 7 | 1 |
| 6 | 2 |
| 5 | 5 |
| 4 | 2 |
| 3 | 1 |
| 2 | 3 |
| 1 | 2 |

---

## 3. Fórmulas relevantes (todas del whitepaper)

### 3.1 Share value

```
s = BLOCKS_PER_EPOCH · R / B  =  360 · R / B       [Sección 10.2]
```

### 3.2 Reward per producer per epoch

```
reward(b) = b · s  =  b · 360 · R / B              [Sección 10.2]
```

### 3.3 Doubling time (whitepaper's own definition)

```
D = BOND_UNIT · B / (S · R)  =  10 · B / (S · R)   [Sección 10.8]
```

### 3.4 Lifetime cumulative reward (derivación estándar)

Bajo dilución constante `d` por época:

```
lifetime_reward(b) = b · s + b · s · (1-d) + b · s · (1-d)² + …
                   = b · s · [1 + (1-d) + (1-d)² + …]
                   = b · s / d
```

Esta es una serie geométrica convergente porque `0 < d < 1`. La suma es
**finita**.

### 3.5 Condición de viabilidad de bondeo

Un productor puede bondear una vez más solo si:

```
b · s / d  ≥  BOND_UNIT
```

Sustituyendo `s = 360 / B`:

```
B  <  36 · b / d
```

---

## 4. Aplicación numérica al estado real

### 4.1 Parámetros

| Variable | Valor | Fuente |
|---|---|---|
| B | 1,891 | RPC getProducers |
| s | 0.1904 | 360/1891 |
| d | 0.0299 | Observado en accuracy log |
| BOND_UNIT | 10 DOLI | Whitepaper 7.2 |
| R | 1.0 | Era 1 |

### 4.2 Lifetime ceilings

```
lifetime(b=1)  =  1 · 0.1904 / 0.0299  =   6.37 DOLI    ← < 10 — WALL
lifetime(b=2)  =  2 · 0.1904 / 0.0299  =  12.74 DOLI    ← 1 more bond, then WALL
lifetime(b=5)  =  5 · 0.1904 / 0.0299  =  31.84 DOLI    ← 3 more bonds, WALL at 8
lifetime(b=10) = 10 · 0.1904 / 0.0299  =  63.68 DOLI    ← 6 more bonds, WALL at 16
```

**Ningún small miner puede llegar ni cerca de 3,000 bonos.** El máximo
teórico alcanzable para el miner más grande (b=10) es 16 bonds,
aproximadamente **0.53% del cap que promete el whitepaper**.

### 4.3 B máximo antes del muro

Para cada cantidad de bonos, el umbral de B más allá del cual el muro
se vuelve absoluto:

```
b=1:   B_max = 36 · 1 / 0.03 = 1,200     ← ya se superó (B=1891)
b=2:   B_max = 36 · 2 / 0.03 = 2,400
b=5:   B_max = 36 · 5 / 0.03 = 6,000
b=10:  B_max = 36 · 10 / 0.03 = 12,000
```

### 4.4 Cronología de muerte de la comunidad

Asumiendo que B crece al ritmo observado (~36 bonos/epoch):

| Grupo | Bonds | B umbral | Epoch del muro | Tiempo |
|---|---|---|---|---|
| 2 miners | 1 | 1,200 | ya walled | 0 |
| 3 miners | 2 | 2,400 | E~64 | ~14 horas |
| 1 miner | 3 | 3,600 | E~98 | ~2 días |
| 2 miners | 4 | 4,800 | E~130 | ~3.5 días |
| 5 miners | 5 | 6,000 | E~163 | ~4.7 días |
| 2 miners | 6 | 7,200 | E~196 | ~6 días |
| 1 miner | 7 | 8,400 | E~230 | ~7.5 días |
| 1 miner | 10 | 12,000 | E~330 | ~12 días |

**Conclusión:** el último small miner muere alrededor de E330, o ~12
días desde E50. **La comunidad completa se extingue en aproximadamente
dos semanas.**

---

## 5. Simulación del caso "un productor de 1 bono entra hoy"

### 5.1 Configuración

- Anchor: E50
- Productor: 1 bond, 0 spendable
- B inicial: 1,891
- Dilución: 2.99% por época (constante, la observada)
- Horizonte: toda Era 1 (35,040 epochs ≈ 4 años)

### 5.2 Resultados

```
E   150 (día 4):    b=1  spendable=5.88  ← se acerca al plateau
E   550 (día 21):   b=1  spendable=6.18  ← plateau alcanzado
E  1050 (día 42):   b=1  spendable=6.18  ← no crece más
E 35090 (4 años):   b=1  spendable=6.18  ← nunca bondeó
```

**El productor termina Era 1 con 1 bond. Nunca bondeó.**

### 5.3 Escenario optimista: dilución decae

Mismo experimento con `d` decayendo linealmente de 3% a 0.1% durante
Era 1:

```
E 1050 (día 42):  b=1  spendable=6.16  ← mismo plateau
E 35090 (4 años): b=1  spendable=~6    ← sigue sin bondear
```

**Mismo resultado.** El plateau ya se formó antes de que la dilución
tenga tiempo de decaer significativamente.

---

## 6. Respuesta a contra-argumentos posibles

### 6.1 "MAX_STAKE es un límite superior. Cuando los structural saturen, la dilución baja y los pequeños recuperan viabilidad."

**Refutado por cronología:** los structural saturan a E566 (~21 días).
Los small miners mueren en 2 semanas. Para cuando los structural liberan
el techo, los small miners llevan una semana walled. Los structural
tampoco se ven obligados a parar de crecer — pueden crear nuevas
identidades con su spendable, manteniendo el techo activo
indefinidamente.

### 6.2 "Los small miners pueden comprar DOLI en el mercado para bondear."

**No refuta el problema:** sí, pueden comprar. Pero la promesa del
whitepaper era explícitamente que "starting with 10 DOLI" es suficiente
para compounding orgánico. Si ese camino no existe, la promesa del
whitepaper es falsa. La "solución" de comprar DOLI transforma DOLI en
un sistema dependiente de capital externo, contradiciendo el pitch
fundacional del paper (Secciones 1, 6.3, 17).

### 6.3 "Los small miners pueden simplemente esperar a que la red madure."

**Matemáticamente imposible:** la serie geométrica `b·s/d` converge en
un número finito. Esperar más tiempo no añade nada después de que la
serie converge (típicamente en días 4-21 del ingreso). El plateau no se
levanta con paciencia.

### 6.4 "La dilución observada (3%) es transitoria; bajará con el tiempo."

**Parcialmente cierto pero irrelevante:** aunque `d` bajara a 0 mañana,
los small miners ya habrían acumulado ~6 DOLI y no podrían bondear. La
serie geométrica ya convergió a su plateau. Lo que importa no es la `d`
futura sino la `d` promedio durante el período en que se acumula
spendable. Como ese período es corto (días), la `d` actual domina el
resultado final.

### 6.5 "Whitepaper dice 'within months' y los números que presentas son 'within days' — no es la misma afirmación."

**Precisamente el punto del dossier:** el whitepaper promete un
mecanismo (compound growth desde 10 DOLI a 3000 bonds in months) que es
demostrablemente imposible bajo las condiciones reales. "Within months"
sería una aspiración si las matemáticas lo permitieran. Las matemáticas
no lo permiten.

### 6.6 "Los small miners pueden usar delegación — el código lo permite."

**Parcialmente cierto, pero confirma la tesis:** `bins/node/src/node/rewards.rs:238-278` implementa delegación donde un small holder delega bonds a un productor grande. Reparto: **90% al productor, 10% al delegador**.

Dos problemas con esta "solución":

1. **No resuelve la matemática del techo**: los rewards del delegador siguen siendo `bonds × (360/B) / d`. La serie sigue convergente. La delegación solo ahorra el costo operativo de un VPS — no levanta el techo.

2. **Contradice el pitch del whitepaper**: la Sección 6.3 promete *"400 TPS on a $5/month VPS — accessibility is sufficient for global participation"*. Si la solución real es "no corras un nodo, delega a uno del equipo", entonces el VPS de $5/mes es decorativo y la descentralización es cosmética.

Si el equipo propone delegación como respuesta, están confirmando que **el modelo "10 DOLI y un VPS" del whitepaper no funciona**, y que la solución real es que los small holders renuncien a ser productores y se conviertan en delegadores pasivos del equipo.

### 6.7 "Pero ACTIVE_PRODUCERS_CAP = 50 limita el problema."

**Falso — empeora el problema:** `crates/core/src/consensus/constants.rs:74` establece que solo los **top 50 productores por attestation** producen bloques. El tier system está activo desde `TIER_SYSTEM_ACTIVATION_HEIGHT = 0`. Los productores fuera del top-50 son "pure attestors" — reciben rewards proporcionales a sus bonds pero no producen bloques.

Esto no cambia la matemática del techo (rewards siguen bond-weighted), pero:

1. **El whitepaper miente por omisión** en Sección 7.3: *"Block production uses pure round-robin — every active producer receives equal block assignments."* Con el cap activo, esto es falso para producers 51+.

2. **Cuando la red pase de 50 productores**, los small miners serán los primeros en caer al tier de "solo attestor" (menor seniority, menor bond count = menor ranking). Actualmente con 29 productores el cap no muerde, pero la arquitectura ya discrimina contra newcomers.

### 6.8 "MAX_REGISTRATIONS_PER_BLOCK = 5 limita el crecimiento."

**Asimétrico a favor de incumbentes:** `consensus/registration.rs:7`. Este cap aplica solo a **nuevas registraciones** (máximo 5 nuevos producers por bloque = 1,800/epoch). **Los producers existentes pueden hacer `AddBond` sin ninguna restricción.**

El efecto neto es:
- Nuevos entrantes (comunidad): limitados a 1,800/epoch
- Incumbentes (equipo): compounding ilimitado

No hay `MAX_BONDS_PER_BLOCK`. Los 12 nodos del equipo pueden hacer miles de `AddBond` por bloque sin límite. Los nuevos producers están puestos en cola.

Esta asimetría no está documentada en el whitepaper y refuerza la tesis del dossier: **el protocolo, tal como está implementado, favorece estructuralmente a los incumbentes sobre los newcomers**.

---

## 7. Preguntas concretas al equipo

Las siguientes preguntas derivan directamente del análisis y no pueden
ser respondidas con argumentos cualitativos. Requieren respuestas
matemáticas o respuestas políticas, pero respuestas al fin.

1. **Sobre la declaración del whitepaper 10.8:** ¿bajo qué condiciones
   específicas `(B₀, d, b₀)` es válida la promesa "reaches 3,000-bond
   cap within months"? ¿Esas condiciones se cumplen en la red actual?
   Si no, ¿por qué se mantiene la promesa en el whitepaper?

2. **Sobre la auto-regulación:** el whitepaper afirma que la red
   "naturally converges toward stable distribution". ¿Cuál es el
   mecanismo específico que fuerza esa convergencia? No hay mención a
   decay, demurrage, bond expiry, treasury, ni rebase. ¿Es una
   afirmación basada en supuestos de comportamiento (asumir que todos
   los productores reinviertan en lockstep)?

3. **Sobre MAX_STAKE y splitting:** ¿es aceptable dentro del protocolo
   que un productor saturado transfiera sus spendable a nuevas
   identidades y las funde como nuevos productores? Si sí, ¿cuál es el
   propósito de MAX_STAKE como límite económico? Si no, ¿dónde está
   documentada la prohibición?

4. **Sobre los small miners actuales:** dado que los 17 small miners
   existentes enfrentan muros de bondeo dentro de 2 semanas bajo las
   condiciones actuales, ¿cuál es el plan del equipo? ¿Se les
   recomienda comprar DOLI? ¿Esperar? ¿Retirar sus bonos?

5. **Sobre el crecimiento futuro de la red:** bajo el modelo actual,
   ¿cómo puede un nuevo participante unirse a la red después de E50 sin
   capital externo? El camino orgánico (compound 10 DOLI) es
   matemáticamente imposible. La única entrada posible es vía compra de
   DOLI en mercado secundario, lo cual no está descrito como mecanismo
   de onboarding en el whitepaper.

---

## 8. Soluciones técnicas posibles

Las siguientes son las tres clases de solución que matemáticamente
resolverían el techo. No son todas políticamente viables, pero son las
únicas opciones honestas.

### 8.1 BOND_UNIT elástico lineal con floor

```
BOND_UNIT(t) = max(FLOOR, 10 · B_genesis / B(t))
```

**Por qué lineal y no logarítmico:** Las simulaciones muestran que
bajo condiciones reales (dilución 3%), la variante lineal es
estrictamente mejor que cualquier variante logarítmica o de raíz. Los
17 small miners actuales, proyectados a 4 años (Era 1 completa):

| Modelo | Bonos finales totales | Ganados |
|---|---|---|
| Current (BU=10 fijo) | 118 | +45 |
| Linear elastic, floor=1 DOLI | 574 | +501 |
| Linear elastic, floor=0.1 DOLI | 2,492 | +2,419 |
| Linear elastic, floor=0.01 DOLI | 10,496 | +10,423 |
| Logarítmico (mejor variante) | ~280 | +207 |

La variante lineal permite que los small miners hagan compounding
efectivo porque **el tiempo de bondeo queda independiente de B**:

```
t_bond = BOND_UNIT(t) / (b · s(t))
       = (10 · B0 / B) / (b · 360 / B)
       = B0 / (36 · b)
```

El `B` se cancela. El tiempo para bondear depende **solo** del número
de bonos del productor, no del tamaño de la red.

**Elección del FLOOR:** trade-off entre inclusión y sybil resistance:

- `FLOOR = 1 DOLI`: 8x mejora sobre el modelo actual. Sybil cost
  mantenido a 10% del actual. Conservador.
- `FLOOR = 0.1 DOLI`: 54x mejora. Sybil cost 1% del actual, pero la
  sybil real ya es cubierta por seniority weight + costo operativo
  (Sección 12.3).
- `FLOOR = 0.01 DOLI`: 230x mejora. Sybil resistance efectivamente
  transferida por completo a los mecanismos no-económicos.

**Recomendación:** `FLOOR = 0.1 DOLI`. Da la mejor relación
inclusión/seguridad en nuestro análisis.

- **Impacto al supply total:** cero
- **Impacto al halving:** cero
- **Impacto a bonders existentes:** ninguno en valor nominal
- **Resolución del techo:** permanente para valores moderados de B
- **Cambio de código:** ~10 líneas

Ver [`refined_proposal.md`](refined_proposal.md) y
[`small_miner_reality.md`](small_miner_reality.md).

### 8.2 Recompensas crecientes por era (inversión del halving)

```
R(era) = R₀ · 2^(era - 1)   en lugar de   R₀ · 0.5^(era - 1)
```

- **Impacto al supply total:** supply se vuelve ilimitado
- **Resolución del techo:** permanente
- **Barrera política:** alta — contradice la narrativa de "scarce
  digital cash"

### 8.3 Demurrage sobre bonos inactivos

Bonos de productores que no atestiguan por N épocas consecutivas se
redistribuyen proporcionalmente a productores activos.

- **Impacto al supply total:** cero
- **Resolución del techo:** permanente
- **Barrera política:** alta — los bonders inactivos pierden valor

---

## 9. Recomendación

Adoptar la **Solución 8.1 (BOND_UNIT elástico lineal con FLOOR=0.1 DOLI)**
por tener el mejor balance entre (a) resolución del problema, (b)
mínimo cambio al protocolo, (c) preservación de las narrativas del
whitepaper (supply fijo, halving intacto), y (d) viabilidad política.

La elección del floor en 0.1 DOLI en lugar de 1.0 DOLI es una decisión
política: da 6x más inclusión a costa de reducir sybil cost nominal de
87,000 DOLI a 8,700 DOLI. Dado que la sybil resistance real viene
principalmente de seniority weight y costo operacional (VPS por
identidad) según el propio whitepaper Sección 12.3, esta reducción en
el componente económico es aceptable.

La alternativa de no hacer nada implica aceptar que:

1. La comunidad orgánica muere en 2 semanas.
2. La red se reduce a los 12 productores del equipo.
3. La promesa del whitepaper sobre compound growth desde 10 DOLI es
   falsa bajo las condiciones actuales.
4. DOLI se vuelve, en la práctica, un sistema de adopción temprana
   cerrada disfrazado de red abierta.

Ninguno de estos cuatro puntos es compatible con las declaraciones
fundacionales del whitepaper (Sección 1: *"a peer-to-peer electronic
cash system"*; Sección 6.3: *"accessibility is sufficient for global
participation"*).

---

## 10. Hallazgos del audit de código fuente

Audit realizado sobre el repo `doli-network/doli` el 2026-04-08.
El objetivo era identificar cualquier mecanismo protocolar que
invalidara las proyecciones de este dossier.

**Resultado del audit: las proyecciones se mantienen. Ningún mecanismo
en el código invalida la matemática del techo.**

Hallazgos confirmados en el código (todos consistentes con el análisis):

### 10.1 Constantes confirmadas (no dinámicas)

| Constante | Valor | Archivo | Estado |
|---|---|---|---|
| `BOND_UNIT` | 10 DOLI | `crates/core/src/consensus/constants.rs:263` | **LOCKED for mainnet** |
| `MAX_BONDS_PER_PRODUCER` | 3,000 | `constants.rs:271` | estático |
| `INITIAL_REWARD` | 1 DOLI/block | `consensus/params.rs` | estático |
| `RewardMode::EpochPool` | activo | `consensus/params.rs:51` | default mainnet |

El archivo `network_params/env_loader.rs:63-65` marca explícitamente el
BOND_UNIT como *"LOCKED for mainnet — consensus-critical"*.

### 10.2 Fórmula de rewards confirmada literalmente

`bins/node/src/node/rewards.rs:14-290`:

```
reward[i] = pool * bonds[i] / Σ(qualifying_bonds)
```

Estrictamente proporcional. Sin bonus, sin floor, sin weighting inverso.
Exactamente lo que asume nuestro modelo del techo.

### 10.3 Mecanismos que NO existen en el código

Verificados explícitamente por grep en todo el repo:

- ❌ **Demurrage / bond decay**: no hay. `INACTIVITY_LEAK_RATE = 10%/epoch`
  está declarado en `constants.rs:181-187` pero **no se invoca desde el
  consensus path**. Es dead code — solo se reporta via RPC, nunca afecta
  el estado.
- ❌ **Treasury / rebate / faucet post-bootstrap**: no hay.
- ❌ **Small producer bonus**: no hay.
- ❌ **Cap dinámico a BOND_UNIT**: no hay.
- ❌ **Redistribución más allá de attestation-based**: no hay.
- ❌ **Cap a bond growth de incumbentes**: no hay.

Las penalizaciones de doble producción son **100% burn**
(`exit.rs:14-19`), no redistribución.

### 10.4 Mecanismos encontrados que NO salvan el análisis

- **Delegación** (`rewards.rs:238-278`): existe, reparte 90% al producer
  y 10% al delegador. No rompe la matemática del techo. Ver 6.6.
- **Tier system** (`constants.rs:74`): `ACTIVE_PRODUCERS_CAP = 50`, ya
  activo. Ver 6.7.
- **Registration cap** (`registration.rs:7`): 5 nuevos por bloque.
  Asimétrico contra newcomers. Ver 6.8.
- **Tier-1/2/3 fallback** (`rewards.rs:75-159`): safety net que evita
  distribuciones de cero. No beneficia a small holders.
- **Vesting penalty** (`exit.rs:84-119`): 75/50/25/0% burn on early exit
  por año. Hace los bonds ilíquidos pero no afecta la dilución.

### 10.5 Discrepancias whitepaper vs código

Estas NO afectan directamente el análisis del techo, pero son evidencia
adicional de que el protocolo descrito en el whitepaper no corresponde
exactamente al protocolo que corre en producción:

1. **`ACTIVE_PRODUCERS_CAP = 50` no está en el whitepaper.** La
   Sección 7.3 afirma *"Block production uses pure round-robin — every
   active producer receives equal block assignments"*. Esto es falso
   para producers ranked 51+.

2. **Tier system activation** (`TIER_SYSTEM_ACTIVATION_HEIGHT = 0`) no
   está documentado en ninguna sección del whitepaper.

3. **Tier-1/2/3 fallback de rewards** (rewards.rs:75-159) no está
   descrito en la Sección 10.2 (*Epoch Reward Distribution*).

4. **Deprecated dead code contradictorio**:
   `crates/core/src/rewards.rs` contiene un `WeightedRewardCalculator`
   con comentarios que dicen *"100% to producer via coinbase"* (líneas
   271-307). Esto contradice el path activo. Es dead code pero es
   evidencia de que el modelo económico ha cambiado sin actualizar el
   whitepaper.

5. **INACTIVITY_LEAK_RATE**: declarado en `constants.rs` pero sin
   invocación en consensus. ¿Está planeado activarlo? ¿Cuándo? ¿Con qué
   proceso de governance? El whitepaper no lo menciona.

### 10.6 Implicación del audit

Las respuestas de Sección 6 (contra-argumentos) incluyen ahora
anticipadamente los hallazgos del audit (6.6 delegación, 6.7 ACTIVE_CAP,
6.8 MAX_REGISTRATIONS asymmetry). El equipo no puede usar ninguno de
estos mecanismos como refutación sin ser consciente de que ya están
abordados.

**Los parámetros económicos que determinan nuestro análisis son
estáticos, están hardcoded, y están marcados como `consensus-critical`
y `LOCKED for mainnet`. Cualquier cambio requeriría un protocol update
bajo Sección 18 (3 de 5 maintainers + <40% veto por bond × seniority
weight).** Dado que el equipo controla ~96% del peso de veto, el
camino técnico para implementar la propuesta de este dossier es
trivial — solo necesita voluntad política.

---

## 11. Reproducibilidad

Todos los números de este dossier se pueden reproducir corriendo:

```bash
cd /Users/dagam/Desktop/doli/openheimer
python3 simulate_ceiling.py     # confirma el techo bajo modelo actual
python3 simulate_elastic.py     # confirma resolución bajo elastic
```

La data de red se obtiene de:
```bash
ssh root@187.124.148.105 \
  'curl -s -X POST http://127.0.0.1:8500 \
   -H "Content-Type: application/json" \
   -d "{\"jsonrpc\":\"2.0\",\"method\":\"getProducers\",\"params\":{\"active_only\":true},\"id\":1}"'
```

Whitepaper original:
```bash
curl -s https://doli.network/WHITEPAPER.md
```

---

*Fin del dossier.*
