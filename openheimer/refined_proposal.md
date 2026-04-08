# Propuesta refinada — el teorema de imposibilidad

> **ACTUALIZACIÓN (2026-04-08):**
>
> La recomendación de este archivo (BOND_UNIT logarítmico) fue
> **incorrecta**. Simulaciones posteriores con la distribución real de
> productores muestran que la variante **lineal** es estrictamente
> mejor que la logarítmica bajo todas las condiciones probadas. El
> argumento del "teorema de imposibilidad" seguía aplicando a modelos
> que intentaban decoupling entre crecimiento de B y BOND_UNIT — pero
> la variante lineal **no** intenta ese decoupling, sino que escala BU
> inversamente con B, lo cual preserva el tiempo de bondeo (`t_bond =
> B0/(36·b)`) como constante independiente de B.
>
> **Recomendación corregida:** `BOND_UNIT = max(0.1, 10·B0/B)`. Ver
> [`dossier.md`](dossier.md) sección 8.1 para justificación.
>
> Este archivo se mantiene como referencia histórica del razonamiento
> que llevó a la corrección.

---


## Lo que el análisis inicial prometió demasiado

La propuesta original era:
```
BOND_UNIT(t) = max(FLOOR, 10 · B0 / B(t))
```
con `FLOOR = 10⁻⁸`.

El problema: bajo la dilución observada de 3% por época, el BOND_UNIT
cae a valores triviales en ~1 mes. La fórmula original "elimina el techo"
pero solo al costo de hacer el bono gratis, lo cual:

1. Rompe la sybil resistance
2. Hace el "bono" un concepto sin contenido económico
3. Crea un incentivo trivial para spam

---

## El teorema implícito

Después de explorar cuatro variantes (lineal, raíz cuadrada, raíz cúbica,
logarítmica), llegué a un resultado incómodo:

> **Bajo las restricciones:**
> **(1) supply total fijo en 25.2M**
> **(2) BOND_UNIT con valor mínimo económicamente significativo**
> **(3) eliminación permanente del techo bajo crecimiento arbitrario de B**
>
> **...es matemáticamente imposible satisfacer las tres a la vez.**

Solo se pueden satisfacer dos:

| Satisface | NO satisface | Ejemplo |
|---|---|---|
| (1) + (2) | (3) | Modelo actual → hay techo |
| (1) + (3) | (2) | Mi primera propuesta → BU crashea |
| (2) + (3) | (1) | Doubling rewards → supply crece |

---

## Comparación de variantes elásticas

Las cuatro formas probadas, con `BOND_UNIT(B)` en DOLI:

| B | LINEAL | √(B0/B) | ∛(B0/B) | 1/(1+ln(B/B0)) |
|---|---|---|---|---|
| 1,712 | 10 | 10 | 10 | 10 |
| 3,424 | 5 | 7.07 | 7.94 | 5.91 |
| 17,120 | 1 | 3.16 | 4.64 | 3.03 |
| 171,200 | 0.1 | 1.00 | 2.15 | 1.78 |
| 1,712,000 | 0.01 | 1.00 | 1.00 | 1.27 |
| 17,120,000 | 0.001 | 1.00 | 1.00 | 1.00 |

La logarítmica es la que más tarda en tocar el piso.

### Tiempo al piso (FLOOR = 1 DOLI)

| Variante | Bajo d=3% compuesto | Bajo lockstep lineal |
|---|---|---|
| Lineal (FLOOR=10⁻⁸) | 753 epochs (~1 mes) | 5.4M años |
| Raíz cuadrada | 157 epochs (6.5 días) | 0.5 años |
| Raíz cúbica | 235 epochs (9.8 días) | 5.4 años |
| **Logarítmica** | **306 epochs (12.8 días)** | **43.6 años** |

Bajo dilución compuesta observada, incluso la logarítmica falla en menos
de 2 semanas. Bajo lockstep del whitepaper, la logarítmica dura más de 40
años antes de tocar el piso.

---

## La pregunta crítica: ¿el 3% es transitorio o permanente?

Todo el análisis depende de esta pregunta.

### Escenario A: El 3% es bootstrap (probable)
La red está en su fase inicial. Nuevos productores entran rápido porque
los primeros DOLI son fáciles de minar y el incentivo de adopción
temprana es alto. Una vez que la adopción se satura, la dilución baja a
0.1%-0.5% por época (comportamiento observado en otras cadenas PoS en
fase madura).

**Implicación:** La fórmula logarítmica funciona durante décadas en este
escenario. El techo efectivo es irrelevante.

### Escenario B: El 3% es permanente (improbable pero posible)
La red nunca se satura — nuevos productores entran continuamente a la
misma tasa que los existentes compoundean. El crecimiento exponencial se
mantiene indefinidamente.

**Implicación:** Ninguna fórmula basada en B puede salvar el modelo. El
BU crashea en semanas, o el techo vuelve.

### Evaluación honesta
El Escenario A es el comportamiento esperado de cualquier red que
"madure". El Escenario B implicaría adopción infinita, lo cual es
imposible físicamente (hay finito número de humanos, finito poder
computacional, finito capital). Así que A es casi seguro.

**Pero no es certeza**, y la propuesta debe ser robusta al escenario B
también.

---

## Propuesta final

```python
def bond_unit(B_current, B_smoothed, B_genesis):
    """Logarithmic elastic BOND_UNIT with hard floor and EMA smoothing."""
    FLOOR = 1.0  # DOLI
    INITIAL = 10.0  # DOLI
    
    if B_smoothed <= B_genesis:
        return INITIAL
    
    elastic_value = INITIAL / (1 + math.log(B_smoothed / B_genesis))
    return max(FLOOR, elastic_value)
```

### Parámetros
- `FLOOR = 1 DOLI` — preserva significado económico y sybil resistance
- `INITIAL = 10 DOLI` — valor de partida idéntico al actual
- `B_smoothed` — media móvil exponencial de B con ventana de 1 semana
  (168 épocas), para inmunizar contra picos de bootstrap
- `B_genesis` — snapshot fijo de B en el momento de activación de la regla

### Lo que garantiza
1. **Nunca baja de 1 DOLI** — sybil resistance preservada en ≥10% del
   valor actual (~8,700 DOLI iniciales, creciendo con B)
2. **Bajo lockstep del whitepaper** — 43 años antes del piso
3. **Bajo bootstrap transitorio** — degradación suave con amortiguación EMA
4. **Después del piso** — sistema idéntico al actual pero con BU=1 DOLI
   (techo empujado ~10x, unos 30 bonds más para VPS1)

### Lo que NO garantiza
1. Eliminación permanente del techo bajo dilución compuesta indefinida
2. Comportamiento diferente si la dilución observada persiste más allá
   de un mes — en ese caso, tocamos el piso y quedamos equivalentes al
   modelo actual con un BU 10x menor

### Cambio al protocolo
Una función `bond_unit()` en el cálculo del costo de registro. ~10
líneas de código. No toca emission, halving, ni supply.

---

## Alternativas radicales si el Escenario B ocurre

Si después del activar la fórmula logarítmica, observamos que la red
sigue creciendo al 3% indefinidamente (y la logarítmica toca el piso en
semanas), necesitamos opciones adicionales. En orden de menor a mayor
disrupción:

### Opción X: Bond marketplace
Hacer los bonos transferibles entre productores. Un nuevo entrante puede
**comprar un bono existente** en lugar de crear uno nuevo. Esto
desacopla el acto de "unirse" del acto de "crear un nuevo slot". B deja
de crecer porque los bonos cambian de manos, no se emiten.

**Cambio protocolar:** mecanismo de transferencia de bonos + un mercado.
**Impacto al supply:** cero. **Impacto al whitepaper:** moderado.

### Opción Y: Cap a la creación de bonos por época
Limitar el número máximo de nuevos registros por época a `K`
(ej. K=50). Exceso pasa a la cola del siguiente epoch. Fuerza a que `B`
crezca a lo sumo linealmente, garantizando la divergencia de la integral
`∫1/B dt` (no techo).

**Cambio protocolar:** sistema de cola de registros.
**Impacto al supply:** cero.
**Impacto al UX:** los nuevos entrantes pueden esperar varias épocas.

### Opción Z: Redistribución de bonos inactivos (demurrage-light)
Bonos de productores que no atestiguan por N épocas consecutivas son
removidos y su capital redistribuido a productores activos. Esto
**reduce B** cuando hay productores inactivos, compensando el
crecimiento.

**Cambio protocolar:** mecanismo de caducidad.
**Impacto al supply:** cero (los DOLI se redistribuyen, no se queman).
**Impacto político:** alto — los bonders inactivos pierden valor.

---

## Recomendación

1. **Implementar la fórmula logarítmica con floor=1 DOLI y EMA.**
   Bajo supuestos realistas (Escenario A) resuelve el problema por
   décadas sin tocar supply, halving ni emission.

2. **Monitorear la dilución observada durante 3-6 meses después de la
   activación.** Si d > 1% per epoch de forma sostenida, activar la
   Opción X (bond marketplace) como capa adicional.

3. **Reservar las Opciones Y y Z como mecanismos de emergencia.** Solo
   si el marketplace no es suficiente y el Escenario B se materializa.

Esta propuesta escalonada es defendible porque cada nivel requiere
evidencia empírica para activarse. No se le pide al equipo que acepte
todo de una vez. Se le pide que acepte el Nivel 1 (logarítmica) como
seguro matemático, con un plan de contingencia si la red se comporta de
forma inesperada.

---

## La honestidad que faltaba en la propuesta original

La propuesta original decía "esto elimina el techo". La verdad es:

> **Esto empuja el techo lo suficiente como para que, bajo cualquier
> escenario razonable, no sea relevante en la vida del protocolo.**

Es una promesa más débil. Es la promesa que las matemáticas permiten
hacer honestamente.

Si el equipo rechaza esta propuesta porque "no elimina el techo
matemáticamente", la respuesta honesta es: **ninguna propuesta con
supply fijo puede hacerlo.** El costo de la garantía matemática es
demurrage o marketplace o cap — y ellos tendrán que elegir cuál de esos
costos están dispuestos a pagar.

No elegir ninguno es elegir el techo actual.
