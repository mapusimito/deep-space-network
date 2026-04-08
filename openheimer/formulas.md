# Fórmulas de DOLI — explicadas

Cada fórmula que usamos para entender y proyectar el comportamiento de la
red. Cada una tiene tres partes:

1. **La fórmula**
2. **Qué representa en lenguaje humano**
3. **De dónde sale (derivación)**

---

## 1. Share value `s`

```
s = BLOCKS_PER_EPOCH / B  =  360 / B
```

### Qué representa
Cuánto DOLI gana **un solo bono** por época, en la Era 1. Si la red tiene
1,712 bonos, entonces `s = 360/1712 ≈ 0.21`. Cada bono cobra 0.21 DOLI por
hora.

### Por qué
En cada época hay 360 bloques. Cada bloque paga 1 DOLI (en Era 1). Total
emitido por época = 360 DOLI. Ese pool se reparte proporcional a los
bonos. Si tú tienes 1 bono de los 1,712 que hay, te toca `1/1712` del
pool, o sea `360/1712 ≈ 0.21 DOLI`.

### Versión con halving
En eras posteriores, la recompensa por bloque baja:
```
s = R · BLOCKS_PER_EPOCH / B  =  R · 360 / B
```
donde `R` es la recompensa por bloque en la era actual (1, 0.5, 0.25...).

---

## 2. Recompensa de un productor

```
reward(b) = b · s = b · 360 / B
```

### Qué representa
Lo que tú ganas en una época si tienes `b` bonos.

### Ejemplo
VPS1 tiene 5 bonos. La red tiene 1,712. Reward = `5 × 0.21 = 1.05 DOLI/época`.

---

## 3. Tasa de dilución `d`

```
d = 1 - (s_nuevo / s_viejo)  =  1 - (B_viejo / B_nuevo)
```

### Qué representa
Cuánto se encoge `s` (tu reward por bono) por época. Si `d = 0.03`, eso
significa que `s` baja 3% por época.

### Por qué importa
Porque el reward por bono baja exponencialmente con `d`. Después de `n`
épocas:
```
s_n = s_0 · (1 - d)^n
```

Y la suma de toda tu vida (geométrica):
```
Total cumulative = s_0 / d
```

Es **finita**. Esa finitud es la fuente del techo.

---

## 4. Reward acumulado de toda la vida (la fórmula del techo)

```
lifetime_reward(b) = b · s / d
```

### Qué representa
La suma de **todos** los rewards que un productor con `b` bonos puede
ganar desde ahora hasta el infinito, asumiendo `d` constante.

### Por qué es finita
Porque viene de la suma de una serie geométrica:
```
b·s + b·s·(1-d) + b·s·(1-d)² + ... 
   = b·s · (1 + (1-d) + (1-d)² + ...)
   = b·s / d
```

La fórmula `1 + r + r² + r³ + ... = 1/(1-r)` con `r = (1-d)` da exactamente
`1/d`. Por eso el resultado tiene `d` en el denominador.

### Aplicación al techo
**Bondear de nuevo es imposible** cuando esta cantidad cae por debajo de
`BOND_UNIT`:
```
b · s / d < 10  →  techo alcanzado
```

Equivalentemente:
```
s < 10 · d / b
```

### Ejemplo numérico (estado actual)
VPS1 con `b=5`, `s=0.21`, `d=0.0299`:
```
lifetime_reward = 5 · 0.21 / 0.0299 = 35.16 DOLI
```
Suficiente para 3 bonos más, después muro.

---

## 5. Tiempo de duplicación (whitepaper, Sección 10.8)

```
D = BOND_UNIT · B / (S · R)
```

donde `S = 60,480 slots/semana` y `R` es el reward por bloque actual.

### Qué representa
Cuántas semanas tarda un productor en duplicar su cantidad de bonos
(asumiendo que `B` se mantenga constante durante esas semanas).

### Por qué el whitepaper se equivoca
Porque `B` **no** se mantiene constante. Mientras tú esperas para
duplicar, el resto del mundo también está bondeando, y `B` crece. Cuando
finalmente llegas al doble de bonos, `B` ya creció también. El "tiempo de
duplicación efectivo" es mucho mayor que `D`.

### Derivación
Reward por semana de un productor con `b` bonos:
```
E(b) = S · R · b / B
```
Para acumular `b · BOND_UNIT` (o sea, suficiente para duplicar):
```
tiempo = (b · BOND_UNIT) / E(b) = (b · 10) / (S · R · b / B) = 10 · B / (S · R)
```
Note que `b` se cancela. De ahí viene la afirmación "D es independiente
de b".

---

## 6. BOND_UNIT elástico (la propuesta)

```
BOND_UNIT(t) = max(FLOOR, BOND_UNIT_INITIAL · B0 / B(t))
```

con `BOND_UNIT_INITIAL = 10 DOLI`, `B0` = bonos al génesis, `FLOOR` = piso
mínimo (ej. `1e-8`, una "wei" de DOLI).

### Qué representa
El costo de un bono **decrece proporcionalmente al crecimiento de la
red**. Si la red duplicó su tamaño desde el génesis, ahora un bono cuesta
la mitad.

### Por qué elimina el techo
El tiempo para acumular un bono nuevo es:
```
t_bond = BOND_UNIT(t) / reward_por_epoca
       = (10 · B0 / B) / (b · 360 / B)
       = 10 · B0 / (360 · b)
       = constante (independiente de B)
```

El `B` se cancela. El tiempo de bondeo deja de depender del tamaño de la
red. Solo depende de `b` (tu cantidad de bonos) y de `R` (la era).

### Por qué la oferta total NO cambia
La fórmula no toca `R` ni la emisión. Los 25,228,800 DOLI siguen
siendo el techo. Solo cambia cuánto te cuesta convertir DOLI líquido en
un slot productivo.

### Por qué la sybil resistance se mantiene
Para controlar 51% de la red:
```
costo_sybil = 0.51 · B · BOND_UNIT(t)
            = 0.51 · B · (10 · B0 / B)
            = 5.1 · B0 DOLI
```

**Constante.** No depende del tamaño actual de la red. La resistencia
queda anclada al valor del génesis. Cumple el rol que el whitepaper le da
al BOND_UNIT (Sección 7.1) sin sacrificar accesibilidad.

---

## 7. Crecimiento de la red (modelo lockstep del whitepaper)

```
dB/dt = S · R / BOND_UNIT  =  60480 · R / 10  =  6048 · R   (bonos por semana)
```

### Qué representa
Si todos los productores reinvierten todo su reward, la red gana ~6,048
bonos por semana en Era 1. Es **lineal**, no exponencial.

### Por qué importa
Porque bajo crecimiento lineal de `B`, la dilución per-epoca decae como
`1/B`:
```
d_lockstep(t) = 36 / B(t)
```

A `B = 1,712`: d ≈ 2.10% por época
A `B = 17,000`: d ≈ 0.21% por época
A `B = 170,000`: d ≈ 0.021% por época

La dilución va a cero asintóticamente. Bajo lockstep estricto, **no hay
techo**. El problema del modelo actual aparece solo cuando `d` no decae —
cuando hay nuevos productores entrando o productores grandes compoundando
desfasadamente.

---

## 8. Crecimiento de la red (modelo compuesto observado)

```
B(t) = B0 · (1 + d)^t
```

### Qué representa
Bajo dilución constante (lo que mi simulador asume), `B` crece
exponencialmente. Esto es lo que pasa cuando hay nuevos productores
entrando continuamente, no solo reinversión.

### Implicación
Bajo crecimiento exponencial, la dilución se mantiene constante en `d`,
y la suma `b · s / d` produce un techo finito. **Este es el escenario
pesimista**, pero también es el que mejor describe la red en su fase
temprana.

---

## 9. Cuándo BOND_UNIT elástico llega al piso

Resolviendo `BOND_UNIT(t) = FLOOR` en cada modelo:

### Bajo dilución compuesta (3%/epoch)
```
FLOOR = 10 · B0 / B(t)
B(t) = 10 · B0 / FLOOR
B0 · (1+d)^t = 10 · B0 / FLOOR
(1+d)^t = 10 / FLOOR
t = log(10 / FLOOR) / log(1 + d)
```

### Bajo lockstep (lineal)
```
FLOOR = 10 · B0 / B(t)
B(t) = 10 · B0 / FLOOR
B0 + 36·t = 10 · B0 / FLOOR
t = (10 · B0 / FLOOR - B0) / 36
```

Ver [`findings.md`](findings.md) para los valores numéricos.

---

## 10. Total supply (no se mueve)

```
total_supply = TOTAL_BLOCKS · R_avg
            ≈ 12,614,400 · (1 + 0.5 + 0.25 + 0.125 + ...) 
            = 12,614,400 · 2 
            ≈ 25,228,800 DOLI
```

### Qué representa
La cantidad total de DOLI que jamás existirán. Es una serie geométrica
convergente (gracias al halving). Por eso es finita, exactamente `25.2M`.

### Importante
**Ninguna de las propuestas de Openheimer toca este número.** El supply
es invariante. Lo único que ajustamos es cuánto cuesta convertir DOLI en
un slot productivo (BOND_UNIT), no cuánto DOLI hay en circulación.
