# Hallazgos de las simulaciones

> **AVISO DE RETRACTACIÓN (2026-04-08):**
>
> Varias conclusiones de este archivo están **desactualizadas o eran
> erróneas**. Específicamente:
>
> 1. **El argumento de "2.66M DOLI atrapados post-saturación" es FALSO.**
>    Los DOLI son transferibles entre direcciones. Un productor saturado
>    puede enviar sus spendable a nuevas identidades y registrar nuevos
>    productores indefinidamente. No existe el "trapping".
>
> 2. **La conclusión de "igualdad perfecta a E9802" es FALSA.** La red no
>    se detiene en 29 productores. El equipo puede spawning nuevos nodos
>    estructurales desde las spendable de los saturados, manteniendo
>    dominancia a perpetuidad.
>
> 3. **El análisis de saturación NO salva a los small miners.** La
>    saturación estructural ocurre en ~21 días, pero los small miners
>    mueren en **días o semanas**, MUCHO antes. Para cuando los
>    estructurales se saturan, los small miners ya están walled.
>
> Ver [`small_miner_reality.md`](small_miner_reality.md) para el análisis
> correcto. Este archivo se mantiene como referencia histórica del error
> de razonamiento.

---

Resultados concretos de correr los modelos contra el estado actual de la
red (anchor E50, B=1712, VPS1=5b, VPS2=5b).

---

## 1. Modelo actual (BOND_UNIT fijo en 10 DOLI)

### Resultado: techo en E122

Bajo el modelo del whitepaper con `BOND_UNIT = 10` constante y dilución
del 3% por época, el bondeo se vuelve **imposible después de E122**.

### Tabla de eventos de bondeo
| Epoch | Gap | Quién | Bonds resultantes | s |
|---|---|---|---|---|
| E56 | +6 | VPS1 | 6 | 0.172 |
| E62 | +6 | VPS2 | 6 | 0.140 |
| E68 | +6 | VPS1 | 7 | 0.115 |
| E76 | +8 | VPS2 | 7 | 0.088 |
| E86 | +10 | VPS1 | 8 | 0.063 |
| E99 | +13 | VPS2 | 8 | 0.040 |
| E122 | +23 | VPS1 | 9 | 0.019 |
| — | ∞ | — | — | — |

Después de E122, los gaps crecen sin límite. La fórmula del techo:
```
ceiling = b · s / d = 9 · 0.019 / 0.0299 = 5.72 DOLI
```
5.72 < 10 (BOND_UNIT). **Muro absoluto.**

---

## 2. Modelo elástico (BOND_UNIT variable)

### Resultado: bondeo nunca se vuelve imposible

Bajo `BOND_UNIT(t) = max(1e-8, 10·B0/B)`, la red sigue bondeando
indefinidamente. De hecho, los gaps **se acortan** con el tiempo.

### Tabla de los primeros eventos
| Epoch | Gap | Quién | Bonds | BOND_UNIT (DOLI) | B |
|---|---|---|---|---|---|
| E55 | +5 | VPS1 | 6 | 8.59 | 1,992 |
| E59 | +4 | VPS2 | 6 | 7.61 | 2,249 |
| E63 | +4 | VPS1 | 7 | 6.74 | 2,540 |
| E66 | +3 | VPS2 | 7 | 6.15 | 2,782 |
| E70 | +4 | VPS1 | 8 | 5.45 | 3,141 |
| E73 | +3 | VPS2 | 8 | 4.97 | 3,441 |
| E76 | +3 | VPS1 | 9 | 4.54 | 3,769 |
| E78 | +2 | VPS2 | 9 | 4.27 | 4,005 |
| E81 | +3 | VPS1 | 10 | 3.90 | 4,387 |
| E83 | +2 | VPS2 | 10 | 3.67 | 4,662 |
| E86 | +3 | VPS1 | 11 | 3.35 | 5,106 |
| E88 | +2 | VPS2 | 11 | 3.15 | 5,426 |
| E90 | +2 | VPS1 | 12 | 2.97 | 5,766 |
| E92 | +2 | VPS2 | 12 | 2.79 | 6,127 |
| E94 | +2 | VPS1 | 13 | 2.63 | 6,510 |

### Estado final (después de ~1.6 meses)
- VPS1 alcanza 1,059 bonos
- VPS2 alcanza 1,058 bonos (cerca del MAX_STAKE = 3,000)
- BOND_UNIT toca el piso de 1e-8 DOLI

**Conclusión:** el modelo elástico no solo elimina el techo, sino que
acelera la acumulación de bonos a medida que la red crece. Los productores
tardíos pueden alcanzar el MAX_STAKE en cuestión de semanas, no años.

---

## 3. ¿Cuándo el costo de un bono "llega a cero"?

El costo del bono es asintótico — nunca llega exactamente a cero, pero
puede caer al piso de representación (1 wei = 10⁻⁸ DOLI).

### Bajo dilución compuesta del 3% por época (modelo observado)

| Costo objetivo | B necesario | Epochs desde anchor | Tiempo |
|---:|---:|---:|---:|
| 10 DOLI | 1,712 | 0 | ahora |
| 5 DOLI | 3,424 | 23 | ~1 día |
| 1 DOLI | 17,120 | 78 | 3.3 días |
| 0.1 DOLI | 171,200 | 156 | 6.5 días |
| 0.01 DOLI | 1,712,000 | 234 | 9.8 días |
| 0.001 DOLI | 17.1M | 312 | 13.0 días |
| 1 wei (10⁻⁸ DOLI) | 1.71 trillones | 753 | ~1 mes |

**Bajo este escenario, el costo unitario del bono se aproxima al
infinitesimal en cosa de un mes.** Esto suena dramático, pero en realidad
no significa que la red colapse — significa que el modelo elástico, en su
forma cruda, sobre-corrige cuando se aplica a una dilución agresiva.
Necesitaría un piso más alto para no degenerar a "bonos gratis".

### Bajo lockstep (modelo del whitepaper)

| Costo objetivo | B necesario | Epochs | Tiempo |
|---:|---:|---:|---:|
| 10 DOLI | 1,712 | 0 | ahora |
| 5 DOLI | 3,424 | 47 | 2 días |
| 1 DOLI | 17,120 | 428 | 18 días |
| 0.1 DOLI | 171,200 | 4,708 | 196 días |
| 0.01 DOLI | 1,712,000 | 47,508 | 5.4 años |
| 0.001 DOLI | 17.1M | 475,508 | 54.3 años |

Bajo el modelo lockstep, el costo del bono baja **lentamente**. Llega a 1
DOLI en 18 días, a 0.1 DOLI en 196 días, a 0.01 DOLI en 5.4 años. Mucho
más manejable.

---

## 4. ¿Cuándo el supply total de DOLI llega a cero?

**Nunca.** El supply total es 25,228,800 DOLI, fijado por la suma
geométrica de los halvings. No baja jamás.

Lo que se aproxima a cero es el **costo de un bono** (no la oferta).
Estos son dos números completamente distintos:

- **Total supply (25.2M)** = cuántos DOLI existen.
- **BOND_UNIT (variable)** = cuántos DOLI cuesta convertir DOLI en un slot
  productivo de productor.

El primero es invariante. El segundo es lo que proponemos hacer elástico
para resolver el techo.

---

## 5. Comparación lado a lado

| Métrica | Modelo actual | Modelo elástico |
|---|---|---|
| Supply total | 25.2M | 25.2M |
| Halvings | Sí | Sí |
| Techo de bondeo | E122 (absoluto) | Nunca |
| Tiempo para llegar a 100 bonos (VPS1) | Imposible | ~E180 |
| Tiempo para MAX_STAKE (3000) | Imposible | ~E1167 (~1.6 meses) |
| Costo absoluto de ataque sybil | Crece sin tope | 5.1·B0 (~8,700 DOLI), constante |
| Bonders existentes pierden valor nominal | No | No |
| Línea de código a cambiar | — | 1 |

---

## 6. Conclusión técnica

Bajo cualquier escenario realista de dilución, el modelo elástico:

1. Elimina por completo el techo de bondeo.
2. No toca el supply total (25.2M sigue intacto).
3. No toca la programación de halvings.
4. Mantiene la sybil resistance en valor absoluto.
5. Requiere modificar **una sola línea** del protocolo.

El único parámetro que necesita afinarse es el **piso** de BOND_UNIT
(`FLOOR`). En la simulación cruda usé 10⁻⁸ y se alcanza en ~1 mes, lo
cual es probablemente demasiado bajo. Un piso más razonable sería entre
0.1 y 1 DOLI, lo cual mantendría el costo nominal alto pero seguiría
permitiendo entrada por décadas o siglos.
