# Openheimer

> *"Now I am become death, the destroyer of bonding ceilings."*

Análisis matemático y económico del modelo de bondeo de DOLI.
Documenta las fórmulas, constantes y simulaciones que usamos para entender
por qué el modelo actual produce un techo de bondeo finito y cómo un
BOND_UNIT elástico lo elimina sin tocar el supply total.

## Contenido

### Documentos principales (leer en orden)

1. **[dossier.md](dossier.md)** — **Dossier formal con análisis completo, fórmulas, simulaciones y preguntas al equipo. Empezar aquí.**
2. **[small_miner_reality.md](small_miner_reality.md)** — Análisis definitivo de por qué los 17 small miners mueren en 2 semanas.
3. **[constants.md](constants.md)** — Constantes del protocolo.
4. **[formulas.md](formulas.md)** — Cada fórmula explicada.

### Documentos de referencia histórica (contienen errores corregidos después)

5. **[findings.md](findings.md)** — Análisis inicial con retractaciones marcadas.
6. **[refined_proposal.md](refined_proposal.md)** — Primera propuesta refinada (logarítmica). Superada por la variante lineal recomendada en el dossier.

### Scripts ejecutables

- **[simulate_ceiling.py](simulate_ceiling.py)** — Confirma el muro bajo el modelo actual.
- **[simulate_elastic.py](simulate_elastic.py)** — Simula el modelo elástico.

## Uso rápido

```bash
# Correr la simulación del modelo elástico (no hay techo)
python3 simulate_elastic.py

# Correr la simulación del modelo actual (encuentra el techo)
python3 simulate_ceiling.py
```

Los dos scripts leen `../projections.json` como estado inicial.
