# VizShifter: Plataforma de Migración Automatizada de QlikView a Microsoft Power BI/Fabric mediante Inteligencia Artificial

## Resumen

La migración de plataformas de Business Intelligence (BI) representa uno de los desafíos técnicos más complejos en la transformación digital empresarial. Este trabajo presenta **VizShifter**, una plataforma de automatización end-to-end que aborda la migración de reportes QlikView hacia Microsoft Power BI y Fabric. El sistema implementa un pipeline de siete etapas que combina automatización de interfaz gráfica (GUI automation), procesamiento de XML, análisis semántico mediante modelos de lenguaje (LLM), generación aumentada por recuperación (RAG) y análisis de imágenes por visión artificial. La plataforma reduce un proceso que típicamente requiere semanas de trabajo manual por reporte a una ejecución automatizada de minutos, manteniendo supervisión humana en puntos críticos de decisión. Los resultados demuestran que la combinación de RAG con modelos GPT-4o produce traducciones de código QlikView Script a M Query y de expresiones QlikView a DAX con calidad suficiente para uso en producción, reduciendo significativamente el esfuerzo manual de migración.

**Palabras clave:** Business Intelligence, migración de plataformas, QlikView, Power BI, RAG, LLM, automatización GUI, traducción de código, DAX, M Query, procesamiento de lenguaje natural.

---

## 1. Introducción

### 1.1 Contexto y Motivación

Las organizaciones que adoptaron QlikView como plataforma de Business Intelligence durante la década de 2010 enfrentan hoy la necesidad de migrar hacia plataformas modernas como Microsoft Power BI y Fabric. Esta necesidad surge por múltiples factores: el fin del ciclo de vida de QlikView, la integración nativa de Power BI con el ecosistema Microsoft 365, las capacidades de colaboración en la nube, y las ventajas económicas del modelo de licenciamiento por usuario de Power BI frente al modelo de accesos concurrentes de QlikView (Gartner, 2024).

Sin embargo, la migración entre plataformas de BI no es trivial. QlikView y Power BI difieren fundamentalmente en su arquitectura de datos, lenguaje de scripting, modelo semántico y paradigma de visualización:

| Aspecto | QlikView | Power BI |
|---------|----------|----------|
| Lenguaje de carga de datos | QlikView Script (QVS) | M Query (Power Query) |
| Lenguaje de expresiones | Expresiones QlikView (set analysis) | DAX (Data Analysis Expressions) |
| Modelo de datos | Modelo asociativo | Modelo tabular (star schema) |
| Almacenamiento | Archivos `.qvw` monolíticos | Datasets, dataflows, lakehouses |
| Metadatos | XML embebido en binario | JSON/TMDL |

Una migración manual típica requiere que un analista: (1) abra cada reporte QlikView, (2) extraiga y documente sus metadatos, (3) comprenda la lógica del script de carga, (4) traduzca manualmente el script a M Query, (5) traduzca cada expresión visual a DAX, (6) reconstruya las visualizaciones en Power BI, y (7) valide que los resultados sean equivalentes. Para organizaciones con decenas o cientos de reportes, este proceso puede requerir meses de trabajo especializado.

### 1.2 Problema de Investigación

El problema central que aborda este trabajo es: **¿Cómo automatizar la migración de reportes QlikView a Power BI minimizando la intervención manual, manteniendo la fidelidad semántica de las traducciones de código, y proporcionando mecanismos de validación objetiva?**

Este problema se descompone en los siguientes subproblemas:

1. **Extracción de metadatos:** QlikView almacena sus metadatos en formato propietario binario accesible únicamente a través de la herramienta DocumentAnalyzer. ¿Cómo automatizar esta extracción a escala?

2. **Traducción de código:** QlikView Script y M Query son lenguajes con paradigmas distintos (imperativo vs. funcional). ¿Pueden los LLMs, aumentados con ejemplos de dominio mediante RAG, producir traducciones de calidad suficiente?

3. **Traducción de expresiones:** Las expresiones QlikView utilizan set analysis, un paradigma sin equivalente directo en DAX. ¿Cómo proporcionar contexto semántico suficiente al LLM para generar DAX correcto?

4. **Validación:** ¿Cómo verificar objetivamente que el reporte migrado es equivalente al original?

### 1.3 Objetivos

**Objetivo General:**
Diseñar e implementar una plataforma de automatización que ejecute el proceso completo de migración de reportes QlikView a Power BI, desde la extracción de metadatos hasta la validación visual del resultado.

**Objetivos Específicos:**

1. Implementar un sistema de extracción automatizada de metadatos QlikView mediante automatización GUI con detección de elementos por template matching.
2. Desarrollar un pipeline de procesamiento que transforme XML jerárquico en estructuras tabulares aptas para análisis y mapeo de tipos.
3. Diseñar e implementar un sistema RAG (Retrieval-Augmented Generation) para la traducción de scripts QlikView a M Query utilizando embeddings y recuperación por similitud coseno.
4. Implementar un traductor de expresiones QlikView a DAX con contexto de modelo semántico e inferencia de tipos.
5. Construir un módulo de exportación visual con procesamiento de imágenes para la extracción de metadatos espaciales.
6. Desarrollar una interfaz web interactiva mediante Streamlit que permita la ejecución, monitorización y visualización de resultados del pipeline.
7. Implementar un sistema de validación visual mediante modelos de visión artificial (GPT-4o Vision) para la comparación automatizada de reportes.

### 1.4 Alcance

El alcance de este trabajo comprende:

- **Incluido:** Migración completa de la capa de datos (scripts de carga), expresiones (medidas DAX), estructura visual (páginas, objetos, posiciones) y metadatos (campos, tipos, relaciones) de reportes QlikView.
- **Excluido:** Recreación automatizada de visualizaciones en Power BI Desktop (requiere interacción con la API de Power BI REST, fuera del alcance actual). La plataforma genera todos los artefactos necesarios para que un desarrollador reconstruya el reporte con mínimo esfuerzo.

---

## 2. Marco Teórico

### 2.1 Business Intelligence y Plataformas de Análisis

Business Intelligence (BI) comprende las estrategias, tecnologías y prácticas para recolectar, integrar, analizar y presentar información empresarial con el objetivo de facilitar la toma de decisiones (Kimball & Ross, 2013). Las plataformas de BI modernas integran capacidades de ETL (Extract, Transform, Load), modelado dimensional, visualización interactiva y distribución de reportes.

**QlikView**, desarrollado por QlikTech (ahora Qlik), introdujo el concepto de modelo asociativo de datos, donde todas las tablas se relacionan automáticamente por campos con nombres coincidentes, eliminando la necesidad de definir joins explícitos. Su lenguaje de scripting propietario permite cargar datos desde múltiples fuentes y transformarlos en memoria.

**Microsoft Power BI** adopta un modelo tabular basado en el motor Vertipaq (Analysis Services), con un esquema estrella (star schema) como patrón recomendado. Utiliza M Query (Power Query) para ETL y DAX (Data Analysis Expressions) para cálculos analíticos. Su integración con Microsoft Fabric extiende sus capacidades hacia lakehouses y flujos de datos empresariales.

### 2.2 Modelos de Lenguaje Grande (LLMs)

Los Modelos de Lenguaje Grande (Large Language Models) son redes neuronales basadas en la arquitectura Transformer (Vaswani et al., 2017) entrenados sobre corpus masivos de texto. Modelos como GPT-4 (OpenAI, 2023) han demostrado capacidades emergentes en comprensión y generación de código, incluyendo traducción entre lenguajes de programación (Chen et al., 2021).

Sin embargo, los LLMs presentan limitaciones críticas para tareas de dominio específico:

- **Alucinación:** Generación de código sintácticamente correcto pero semánticamente incorrecto.
- **Conocimiento desactualizado:** El training data puede no incluir lenguajes de nicho como QlikView Script.
- **Falta de contexto:** Sin información sobre el esquema de datos específico, las traducciones pueden ser genéricamente correctas pero inaplicables al caso particular.

### 2.3 Generación Aumentada por Recuperación (RAG)

RAG (Retrieval-Augmented Generation) es una técnica que combina la recuperación de información relevante desde una base de conocimiento con la capacidad generativa de un LLM (Lewis et al., 2020). El proceso consiste en:

1. **Indexación:** Convertir documentos de la base de conocimiento en vectores de embedding mediante un modelo de embeddings (e.g., `text-embedding-3-small`).
2. **Recuperación:** Ante una consulta, computar su embedding y recuperar los k documentos más similares por distancia coseno.
3. **Generación aumentada:** Inyectar los documentos recuperados como contexto adicional en el prompt del LLM.

RAG mitiga las limitaciones de los LLMs al proporcionar ejemplos de dominio actualizados sin necesidad de fine-tuning, reduciendo alucinaciones y mejorando la calidad de las respuestas en dominios especializados.

### 2.4 Automatización de Interfaces Gráficas

La automatización GUI (Graphical User Interface) permite controlar aplicaciones de escritorio programáticamente mediante la simulación de eventos de teclado y ratón. Herramientas como PyAutoGUI (Sweigart, 2019) implementan template matching basado en OpenCV para la detección de elementos de interfaz independiente de la resolución.

Esta técnica es necesaria cuando la aplicación objetivo no expone una API programática, como es el caso de QlikView DocumentAnalyzer, una herramienta propietaria que solo opera a través de su interfaz gráfica.

### 2.5 Procesamiento de Documentos y Visión Artificial

Los modelos multimodales como GPT-4o Vision (OpenAI, 2024) permiten analizar imágenes con comprensión semántica. En el contexto de BI, esto habilita la extracción estructurada de información desde capturas de pantalla de reportes: identificación de KPIs, tipos de gráficos, filtros activos y esquemas de color.

---

## 3. Diseño y Arquitectura del Sistema

### 3.1 Arquitectura General

VizShifter implementa una arquitectura de pipeline secuencial con siete etapas independientes, cada una consumiendo los artefactos producidos por las etapas anteriores. El diseño sigue los principios de:

- **Idempotencia:** Cada etapa puede re-ejecutarse sin efectos secundarios adversos.
- **Degradación graceful:** El pipeline continúa procesando con los datos disponibles aunque algunas fuentes intermedias falten.
- **Procesamiento incremental:** Solo se reprocesan archivos que han cambiado, detectado mediante hashing SHA-256.
- **Trazabilidad:** Cada ejecución se registra en un log estructurado (JSON) con estado por archivo.

```
                          ┌─────────────────────────────────┐
                          │         Interfaz Streamlit       │
                          │   (Ejecución, Monitoreo, Viz)   │
                          └──────────┬──────────────────────┘
                                     │
            ┌────────────────────────┼────────────────────────┐
            │                   PIPELINE                      │
            │                                                 │
            │  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
            │  │ Etapa 1  │→│ Etapa 2  │→│ Etapa 3  │     │
            │  │ Metadata │  │ XML Parse│  │ Mapping  │     │
            │  └──────────┘  └──────────┘  └──────────┘     │
            │       │              │             │            │
            │       ▼              ▼             ▼            │
            │  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
            │  │ Etapa 4  │  │ Etapa 5  │  │ Etapa 6  │     │
            │  │ M Query  │  │   DAX    │  │   PDF    │     │
            │  │  (RAG)   │  │  (LLM)   │  │ Export   │     │
            │  └──────────┘  └──────────┘  └──────────┘     │
            │       │              │             │            │
            │       └──────────────┼─────────────┘            │
            │                      ▼                          │
            │               ┌──────────┐                      │
            │               │ Etapa 7  │                      │
            │               │ Síntesis │                      │
            │               │  JSON    │                      │
            │               └──────────┘                      │
            │                                                 │
            └─────────────────────────────────────────────────┘
                                     │
                          ┌──────────┴──────────┐
                          │   Azure OpenAI API   │
                          │  GPT-4o + Embeddings │
                          └─────────────────────┘
```

### 3.2 Estructura del Proyecto

```
ai_bi_platform_migration/
├── src/
│   ├── app.py              # Interfaz web Streamlit
│   ├── main.py             # Punto de entrada CLI
│   ├── executor.py         # Orquestador del pipeline (7 etapas)
│   └── utils/
│       ├── llm.py          # Integración LLM, RAG, embeddings, visión
│       ├── parsing.py      # Procesamiento XML, aplanamiento, mapeo
│       ├── io_helpers.py   # I/O, caché, PDF, SharePoint
│       ├── gui.py          # Automatización GUI (QlikView, Power BI)
│       └── tracking.py     # Logging, ejecución, métricas
├── assets/
│   ├── rag/
│   │   └── m_query_rag.txt # Base de conocimiento RAG
│   ├── mapping/
│   │   ├── field_mapping.csv
│   │   └── Object_Types_Classification.csv
│   └── ui/                 # Recursos gráficos
├── demo_output/            # Datos demo para despliegue cloud
├── .streamlit/
│   └── config.toml         # Configuración tema Streamlit
└── requirements.txt
```

### 3.3 Modelo de Datos

El sistema opera sobre tres niveles de representación de datos:

1. **Nivel Fuente:** Archivos `.qvw` binarios de QlikView, accesibles únicamente mediante DocumentAnalyzer.

2. **Nivel Intermedio:** Artefactos CSV y XML extraídos y transformados progresivamente:
   - `objects.csv` — Inventario de objetos visuales (gráficos, tablas, selectores)
   - `expressions.csv` — Expresiones visuales con metadatos de contexto
   - `fields.csv` — Campos del modelo de datos con tipos y relaciones
   - `sheets.csv` — Hojas del reporte con dimensiones
   - `script.qvs` — Script de carga de datos (UTF-16)
   - `Document/*.xml` — Descriptores XML por objeto visual

3. **Nivel Destino:** Artefactos JSON enriquecidos listos para consumo por Power BI:
   - `enriched_dax.json` — Objetos con expresiones DAX traducidas
   - `m_query_output.json` — Tablas M Query por fuente de datos
   - `report_pages.json` — Páginas del reporte con imágenes y metadatos espaciales

---

## 4. Implementación

### 4.1 Etapa 1: Extracción Automatizada de Metadatos

**Problema:** QlikView almacena sus metadatos en formato binario propietario dentro del archivo `.qvw`. La única forma de extraerlos es mediante la herramienta DocumentAnalyzer, que opera exclusivamente a través de su interfaz gráfica.

**Solución:** Automatización GUI mediante PyAutoGUI con detección de elementos por template matching.

**Algoritmo:**

```
PARA CADA archivo .qvw EN directorio_fuente:
    hash ← SHA-256(archivo)
    SI hash == cache[archivo].hash Y existe(carpeta_salida):
        SALTAR (archivo no ha cambiado)
    
    SI ventana_DocumentAnalyzer NO existe:
        LANZAR DocumentAnalyzer
        ESPERAR ventana visible
    
    LOCALIZAR campo_ruta POR template_matching(path_input_anchor.png, confianza=0.8)
    SI NO encontrado:
        USAR coordenadas_respaldo  // Fallback para resoluciones no estándar
    
    ESCRIBIR ruta_qvw EN campo_ruta
    LOCALIZAR botón_extraer POR template_matching(extract_button.png, confianza=0.8)
    CLICK botón_extraer
    ESPERAR extracción_completa
    
    ACTUALIZAR cache[archivo] ← {hash, timestamp}
```

**Optimizaciones implementadas:**

- **Reutilización de ventana:** DocumentAnalyzer se mantiene abierto entre archivos, ahorrando ~10 segundos por archivo en el ciclo de apertura/cierre.
- **Caché por hash SHA-256:** Solo se reprocesan archivos cuyo contenido ha cambiado, evitando re-extracciones innecesarias en ejecuciones incrementales.
- **Detección de cambios por mtime:** Antes de calcular el hash (operación costosa para archivos grandes), se verifica si el timestamp de modificación ha cambiado.
- **Reintentos con backoff exponencial:** Multiplicadores de 0.5, 1.0 y 2.0 para manejar fallos transitorios de la GUI.

**Salida:** Por cada archivo `.qvw`, se genera una carpeta con:

| Archivo | Contenido |
|---------|-----------|
| `objects.csv` | Inventario completo de objetos visuales |
| `objectSheets.csv` | Relación objeto-hoja |
| `sheets.csv` | Hojas del reporte con dimensiones |
| `expressions.csv` | Expresiones visuales con contexto |
| `fields.csv` | Campos del modelo con tipos y tags |
| `script.qvs` | Script de carga de datos (UTF-16) |
| `Document/*.xml` | Descriptor XML por objeto visual |

### 4.2 Etapa 2: Parsing y Aplanamiento XML

**Problema:** Los descriptores XML de QlikView son estructuras profundamente anidadas (5-8 niveles) que no son directamente analizables con herramientas tabulares.

**Solución:** Aplanamiento recursivo mediante recorrido en profundidad (DFS) con concatenación de claves.

**Algoritmo de aplanamiento:**

```
FUNCIÓN aplanar(diccionario, prefijo="", separador="_"):
    resultado ← {}
    PARA CADA (clave, valor) EN diccionario:
        nueva_clave ← prefijo + separador + clave SI prefijo SINO clave
        SI valor ES diccionario:
            resultado ← resultado ∪ aplanar(valor, nueva_clave, separador)
        SI NO SI valor ES lista:
            PARA CADA (índice, elemento) EN enumerar(valor):
                SI elemento ES diccionario:
                    resultado ← resultado ∪ aplanar(elemento, nueva_clave + "_" + índice)
                SI NO:
                    resultado[nueva_clave + "_" + índice] ← elemento
        SI NO:
            resultado[nueva_clave] ← valor
    RETORNAR resultado
```

**Detección de encoding:** Se utiliza `chardet` para detectar automáticamente la codificación del archivo XML (UTF-8, UTF-16, Latin-1), dado que QlikView genera archivos en diferentes encodings según la configuración regional.

**Análisis de frecuencia de campos:** Se mantiene un `defaultdict(set)` que registra en cuántos objetos aparece cada campo, generando `objects_all_fields.csv` como referencia para la etapa de mapeo.

**Salida:** Un CSV por objeto XML (e.g., `LB01.csv`, `CH02.csv`) con estructura plana de una fila y N columnas.

### 4.3 Etapa 3: Mapeo de Campos QlikView → Power BI

**Problema:** Los CSVs aplanados contienen cientos de atributos por objeto, de los cuales solo un subconjunto es relevante para la reconstrucción en Power BI.

**Solución:** Tabla de mapeo predefinida con 93 entradas que asocia prefijos de objetos QlikView con tipos Power BI equivalentes y filtra los atributos relevantes.

**Tabla de mapeo (extracto):**

| Prefijo QlikView | Tipo QlikView | Tipo Power BI Equivalente | Campos Relevantes |
|-------------------|---------------|---------------------------|-------------------|
| CH | Chart | Visualization | GraphProperties, Dimensions, Measures |
| LB | ListBox | Slicer | Frame_Rect, Field, Selection |
| TB | Table Box | Table | Frame_Rect, Fields, Columns |
| TX | Text Object | Text Box | Text_v, Frame_Rect, Font |
| BU | Button | Button | Text_v, Actions, Frame_Rect |
| SB | Statistics Box | Card / KPI | Frame_Rect, Statistics |
| SO | Sheet Object | Container | Frame_Rect, Children |

**Transformación pivote:** Los CSVs en formato ancho (una fila, muchas columnas) se transforman a formato largo (atributo/valor) para facilitar el análisis posterior:

```
Formato ancho:  CH01_Title | CH01_Type | CH01_Color | ...
                "Ventas"   | "Bar"     | "#7c3aed"  | ...

Formato largo:  atributo       | valor
                CH01_Title     | "Ventas"
                CH01_Type      | "Bar"
                CH01_Color     | "#7c3aed"
```

**Salida:** `{objeto}_mapped_pivoted.csv` por cada objeto visual.

### 4.4 Etapa 4: Traducción de Scripts a M Query mediante RAG

**Problema:** QlikView Script (QVS) es un lenguaje imperativo de carga de datos con constructos sin equivalente directo en M Query (Power Query), un lenguaje funcional. La traducción zero-shot por un LLM produce resultados inconsistentes debido a la especificidad del dominio.

**Solución:** RAG (Retrieval-Augmented Generation) con base de conocimiento de ejemplos QVS→M Query anotados manualmente.

**Arquitectura RAG implementada:**

```
┌─────────────────────────────────────────────────────┐
│                 Base de Conocimiento                 │
│              m_query_rag.txt (N pares)              │
│                                                      │
│  Ejemplo 1: [QVS input] → [M Query output]         │
│  Ejemplo 2: [QVS input] → [M Query output]         │
│  ...                                                 │
└──────────────────┬──────────────────────────────────┘
                   │ text-embedding-3-small
                   ▼
┌─────────────────────────────────────────────────────┐
│              Índice de Embeddings                    │
│         embedding_index.json (1536-dim)             │
└──────────────────┬──────────────────────────────────┘
                   │
    Consulta: tab de script QVS del usuario
                   │ embed → similitud coseno
                   ▼
┌─────────────────────────────────────────────────────┐
│           Top-k Ejemplos Recuperados                 │
│     (inyectados como few-shot demonstrations)       │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│              Azure OpenAI GPT-4o                     │
│         (temperatura=0.5, few-shot prompt)           │
│                                                      │
│  System: Reglas de traducción QVS→M + ejemplos      │
│  User: Script QVS del tab actual                    │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│              Post-procesamiento                      │
│    Regex extraction: (TableName, MQueryScript)       │
│              → m_query_output.csv                    │
└─────────────────────────────────────────────────────┘
```

**Algoritmo detallado:**

1. **Segmentación del script:** El script `.qvs` se divide por marcadores de tab (`///$tab TabName`) mediante regex, generando segmentos independientes que se traducen por separado.

2. **Construcción del índice de embeddings:**
   - Se parsea `m_query_rag.txt` extrayendo pares (input QVS, output M Query).
   - Cada input se embebe con `text-embedding-3-small` (dimensión 1536).
   - El índice se persiste en `embedding_index.json` para reutilización.

3. **Recuperación por similitud coseno:**
   ```
   similitud(a, b) = (a · b) / (||a|| × ||b||)
   ```
   Se recuperan los `top_k` ejemplos más similares al tab de código QVS actual.

4. **Generación aumentada:** Los ejemplos recuperados se inyectan en el prompt del sistema como demostraciones few-shot, proporcionando al LLM patrones de traducción específicos del dominio.

5. **Post-procesamiento:** La respuesta del LLM se procesa con regex para extraer bloques estructurados `(TableName, MQueryScript)`.

**Reglas de traducción codificadas en el prompt del sistema:**

| Constructo QVS | Equivalente M Query |
|-----------------|---------------------|
| `LOAD ... FROM [archivo.qvd]` | `Qvd.Document(file)` |
| `LOAD ... FROM [archivo.xlsx]` | `Excel.Workbook(file)` |
| `SQL SELECT ... FROM ...` | `Sql.Database(server, db)` |
| `RESIDENT tabla` | `Table.SelectRows(tabla, ...)` |
| `CONCATENATE` | `Table.Combine({tabla1, tabla2})` |
| `JOIN` | `Table.Join(...)` |
| `INLINE [...]` | `#table(columns, rows)` |

**Salida:** `m_query_output.csv` con una fila por tabla M Query generada.

### 4.5 Etapa 5: Traducción de Expresiones a DAX

**Problema:** Las expresiones QlikView utilizan set analysis (`{<Field={Value}>}`) y funciones de agregación con sintaxis diferente a DAX. Una traducción correcta requiere conocimiento del esquema de datos (nombres de tablas, tipos de campos, relaciones).

**Solución:** Extracción automática del modelo semántico desde `fields.csv` e inyección como contexto en el prompt del LLM.

**Extracción del modelo semántico:**

```
FUNCIÓN obtener_modelo_semántico(fields_csv):
    campos ← leer_csv(fields_csv)
    campos ← filtrar(campos, FieldTableCount > 0)  // Solo campos activos
    
    tablas ← {}
    relaciones ← []
    
    PARA CADA campo EN campos:
        tipo_dax ← inferir_tipo(campo.FieldTags)
        // Reglas de inferencia:
        //   "$timestamp" o "$date" → DateTime
        //   "$numeric"            → Whole Number
        //   "$currency"           → Currency
        //   "$text"               → Text
        //   default               → Text
        
        PARA CADA tabla EN campo.FieldTables:
            tablas[tabla].agregar({campo.nombre, tipo_dax})
        
        SI campo.FieldTableCount > 1:
            // Campo aparece en múltiples tablas → posible clave de relación
            relaciones.agregar(campo)
    
    RETORNAR esquema_formateado(tablas, relaciones)
```

**Ejemplo de modelo semántico generado:**

```
Tables:
  'FactFlights': [
    FlightID (Whole Number),
    AirlineCode (Text),
    Revenue (Currency),
    FlightDate (DateTime)
  ]
  'DimAirline': [
    AirlineCode (Text),
    AirlineName (Text),
    Country (Text)
  ]

Relationships:
  'FactFlights'[AirlineCode] → 'DimAirline'[AirlineCode]
```

**Control de tasa (Rate Limiting):**

Para respetar los límites de la API de Azure OpenAI (150 solicitudes/minuto), se implementa una ventana deslizante de timestamps de solicitudes con backoff automático:

```
FUNCIÓN verificar_limite():
    ahora ← timestamp_actual()
    ventana ← filtrar(solicitudes, timestamp > ahora - 60s)
    SI longitud(ventana) >= 150:
        espera ← ventana[0].timestamp + 60s - ahora
        DORMIR(espera)
```

**Marcado de baja confianza:** Las traducciones que el modelo indica con confianza inferior al 80% se marcan como `"**-Needs manual attention-**"` para revisión humana.

**Salida:**
- `expressions_with_dax.csv` — Expresiones originales con DAX traducido lado a lado.
- `DAX_output.csv` — Solo las medidas DAX generadas.

### 4.6 Etapa 6: Exportación de Páginas como Imágenes

**Problema:** Para validación visual y documentación, se necesitan imágenes de alta calidad de cada página del reporte QlikView, con metadatos espaciales que faciliten la reconstrucción del layout en Power BI.

**Solución:** Automatización GUI para exportar a PDF, seguida de conversión a PNG con procesamiento de imagen.

**Pipeline de procesamiento de imagen:**

```
PDF (QlikView print) 
  → PyMuPDF render @ 300 DPI
    → Detección de color de fondo
      → Máscara alfa (fondo → transparente)
        → Detección de bounding box de contenido
          → Recorte inteligente
            → PNG final + metadatos espaciales
```

**Metadatos espaciales generados:**

```json
{
  "page": 1,
  "sheet_name": "Dashboard",
  "file_name": "01_Dashboard.png",
  "full_size_px": [2480, 3508],
  "content_bbox_px": [120, 85, 2350, 3400],
  "content_size_px": [2230, 3315],
  "content_size_cm": [18.88, 28.07],
  "relative_position": {
    "x": 0.048,
    "y": 0.024,
    "width": 0.899,
    "height": 0.945
  }
}
```

Las coordenadas normalizadas (0-1) permiten la reconstrucción del layout en cualquier resolución destino.

**Salida:**
- `ReportPages/{página}_{hoja}.png` — Imagen recortada por página.
- `ReportPages/page_dimensions.json` — Metadatos espaciales.

### 4.7 Etapa 7: Síntesis de Salida Estructurada

**Problema:** Los artefactos de las etapas 1-6 están dispersos en múltiples CSVs y JSONs con esquemas heterogéneos. Se necesita una vista unificada y enriquecida para consumo downstream.

**Solución:** Integración multi-fuente mediante joins de pandas con degradación graceful.

**Proceso de integración:**

```
objects.csv ──────┐
objectSheets.csv ─┤
sheets.csv ───────┤
                  ├──→ MERGE (left joins) ──→ enriched_dax.json
expressions.csv ──┤
DAX_output.csv ───┤
field_mapping.csv ┘

m_query_output.csv ──→ normalización ──→ m_query_output.json

ReportPages/*.png ────→ listado ──→ report_pages.json
```

**Degradación graceful:** Si alguna fuente intermedia no existe (e.g., no se ejecutó la etapa de DAX), el sistema continúa con los datos disponibles, registrando advertencias en el log. Esto permite obtener resultados parciales útiles sin requerir la ejecución completa del pipeline.

**Estructura del JSON enriquecido:**

```json
[
  {
    "ObjectId": "CH01",
    "ObjectName": "Revenue by Region",
    "SheetName": "Dashboard",
    "ObjectTypeQlikView": "Chart",
    "ObjectTypePowerBI": "Visualization",
    "Position": {"x": 0.05, "y": 0.10, "width": 0.45, "height": 0.40},
    "Expressions": [
      {
        "Original": "Sum(Revenue)",
        "DAX": "SUMX(FactSales, FactSales[Revenue])",
        "Confidence": "High"
      }
    ]
  }
]
```

### 4.8 Análisis de Complejidad de Migración (Migration Complexity Analysis)

**Problema:** Antes de iniciar una migración, los equipos necesitan estimar el esfuerzo requerido y priorizar qué reportes migrar primero. Sin una evaluación objetiva, la planificación se basa en intuición, lo que lleva a subestimaciones y retrasos.

**Solución:** Un módulo de feature engineering y scoring multi-criterio que analiza cuantitativamente los metadatos ya extraídos por el pipeline para producir un índice de complejidad de migración.

**Arquitectura del scoring:**

```
┌─────────────────────────────────────────────────────────┐
│              Fuentes de Datos (7 archivos)               │
│  fields.csv │ expressions.csv │ script.qvs │ objects.csv │
│  sheets.csv │ objectSheets.csv│ dimensions.csv           │
└──────────────────┬──────────────────────────────────────┘
                   │ Feature Extraction
                   ▼
┌─────────────────────────────────────────────────────────┐
│            27 Features en 4 Dimensiones                  │
│                                                          │
│  Data Model (30%)  │  Expressions (25%)                  │
│  • field_count     │  • expression_count                 │
│  • key_field_count │  • has_set_analysis                 │
│  • avg_cardinality │  • nested_function_depth            │
│  • multi_table_... │  • aggregation_diversity            │
│                    │                                      │
│  Script (25%)      │  Layout (20%)                       │
│  • line_count      │  • object_count                     │
│  • join_count      │  • sheet_count                      │
│  • has_loops       │  • chart_count                      │
│  • tab_count       │  • dimension_count                  │
└──────────────────┬──────────────────────────────────────┘
                   │ Min-Max Normalisation
                   │ (predefined reference ranges)
                   ▼
┌─────────────────────────────────────────────────────────┐
│         Two-Level Weighted Aggregation                    │
│                                                          │
│  Level 1: feature weights → dimension score (0-100)     │
│  Level 2: dimension weights → overall score (0-100)     │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│  Classification: Low (<25) │ Medium (25-50)              │
│                  High (50-75) │ Critical (>75)           │
│  + Effort Estimation (person-days)                       │
│  + Contextual Recommendations                            │
└─────────────────────────────────────────────────────────┘
```

**Algoritmo de normalización:**

A diferencia de la normalización estándar basada en datos (z-score o percentiles), que requiere un conjunto de datos suficientemente grande, este sistema utiliza **rangos de referencia predefinidos** basados en conocimiento de dominio de migraciones QlikView. Esto permite producir scores válidos e interpretables con un solo reporte (N=1), siguiendo el enfoque de índices de complejidad de software como McCabe (1976) y Halstead (1977).

```
normalizar(valor, mín, máx) = clamp((valor - mín) / (máx - mín), 0, 1)
```

Donde `mín` y `máx` representan los extremos típicos observados en reportes QlikView reales (e.g., `field_count`: rango [5, 200]; `join_count`: rango [0, 10]).

**Agregación ponderada en dos niveles:**

```
score_dimensión = Σ (feature_normalizada_i × peso_feature_i) × 100

score_global = Σ (score_dimensión_j × peso_dimensión_j)
```

Los pesos de las dimensiones reflejan su impacto relativo en el esfuerzo de migración:
- **Modelo de Datos (30%):** La complejidad del modelo (campos, relaciones, cardinalidad) determina el esfuerzo de reconstrucción del semantic model en Power BI.
- **Expresiones (25%):** Expresiones con set analysis o funciones anidadas requieren traducción manual a DAX.
- **Script (25%):** JOINs, loops y subrutinas en el script de carga tienen traducciones no triviales a M Query.
- **Layout (20%):** La densidad visual (objetos por hoja, tipos diversos) afecta el esfuerzo de reconstrucción de dashboards.

**Extracción de features por dimensión:**

| Dimensión | Feature | Método de Extracción | Relevancia |
|-----------|---------|---------------------|------------|
| Data Model | `field_count` | `len(fields.csv)` | Tamaño del modelo |
| Data Model | `key_field_count` | FieldTags contiene `$key` | Claves de relación |
| Data Model | `measure_field_count` | `$numeric` AND NOT `$key` | Medidas a traducir |
| Data Model | `avg_cardinality` | `mean(FieldValueCount)` | Volumen de datos |
| Data Model | `multi_table_fields` | `FieldTableCount > 1` | Complejidad de joins |
| Data Model | `type_diversity` | Tags únicos (`$key`, `$numeric`, `$date`...) | Heterogeneidad |
| Expressions | `expression_count` | `len(expressions.csv)` | Volumen de trabajo |
| Expressions | `has_set_analysis` | regex `\{<` en Expression | Patrón QlikView sin equivalente directo |
| Expressions | `nested_function_depth` | `max(count("("))` por expresión | Profundidad lógica |
| Expressions | `aggregation_diversity` | funciones únicas (Sum, Count, Avg...) | Variedad de cálculos |
| Expressions | `dax_translation_gap` | `1 - (traducidas / total)` | Cobertura de traducción |
| Script | `join_count` | regex `\bJOIN\b` en script.qvs | Complejidad de ETL |
| Script | `has_loops` | regex `\bFOR\|DO WHILE\b` | Sin equivalente en M Query |
| Script | `has_subroutines` | regex `\bSUB\b` | Requiere refactoring |
| Layout | `max_objects_per_sheet` | `max(groupby SheetId)` | Densidad visual |
| Layout | `chart_count` | ObjectType in {7,10,11,12,13} | Visualizaciones a recrear |

**Generación de recomendaciones:** El sistema genera recomendaciones contextuales basadas en qué dimensiones superan el umbral de 50 puntos, identificando riesgos específicos como JOINs sin equivalente directo, loops que requieren reescritura manual, o modelos de datos con excesivas claves de relación.

**Resultado para el caso de estudio (Airline Operations):**

| Dimensión | Score | Interpretación |
|-----------|-------|----------------|
| Data Model | 45.0 | Moderado — 63 campos, 7 join keys |
| Expressions | 4.4 | Bajo — 8 expresiones Sum() simples |
| Script | 11.4 | Bajo — sin JOINs, sin loops |
| Layout | 27.4 | Moderado — 23 objetos, 2 hojas |
| **Overall** | **22.9** | **Low — migración directa, 1-3 persona-días** |

**Significancia académica:** Este módulo constituye una contribución de data science al proyecto: feature engineering sobre metadatos heterogéneos, normalización con rangos de referencia de dominio (siguiendo la tradición de métricas de complejidad de software), y scoring multi-criterio ponderado. A diferencia de los pasos basados en LLM, este análisis es determinista, reproducible y no depende de APIs externas.

### 4.9 Sistema de Trazabilidad y Logging

Cada ejecución del pipeline genera un registro detallado en `execution_log.json`:

```json
{
  "extract_qv_metadata": {
    "step_name": "extract_qv_metadata",
    "last_run": "2025-05-10T14:23:45",
    "status": "success",
    "duration_sec": 245.67,
    "files": [
      {
        "file": "Airline_Operations",
        "finished_at": "2025-05-10T14:27:30",
        "duration_sec": 120.5,
        "status": "success"
      }
    ]
  }
}
```

El sistema implementa **fallo pegajoso (sticky failure):** si cualquier archivo falla en una etapa, el estado de la etapa completa se marca como `failed`, permitiendo la detección downstream de fallos parciales.

---

## 5. Interfaz de Usuario

### 5.1 Diseño de la Interfaz Web

La plataforma ofrece una interfaz web construida con Streamlit que permite:

1. **Ejecución del pipeline:** Selección de etapas individuales o ejecución completa, con opciones de sobrescritura por etapa.
2. **Monitoreo en tiempo real:** Barra de estado con progreso por etapa y reporte de resultados por archivo.
3. **Visualización de resultados:** Tabs para explorar expresiones DAX, tablas M Query e imágenes de páginas de reportes.
4. **Historial de ejecuciones:** Panel con estado, duración y detalle por archivo de cada ejecución.
5. **Reporte Power BI embebido:** Iframe interactivo con el reporte Power BI generado.

### 5.2 Modo Cloud vs. Modo Local

La aplicación detecta automáticamente su entorno de ejecución:

```python
CLOUD_MODE = sys.platform != "win32"
```

| Funcionalidad | Modo Local (Windows) | Modo Cloud (Linux) |
|---------------|---------------------|-------------------|
| Ejecución del pipeline | Disponible | No disponible (sin GUI) |
| Visualización de resultados | Datos en vivo | Datos demo |
| Análisis de complejidad | Disponible | Disponible (datos demo) |
| Panel de logs | Disponible | No disponible |
| Carga a SharePoint | Disponible | No disponible |
| Reporte Power BI | Embebido | Embebido |
| Info del pipeline | Disponible | Disponible |

Esta separación permite desplegar la aplicación en Streamlit Cloud como demostración interactiva sin requerir infraestructura Windows.

---

## 6. Tecnologías y Herramientas

### 6.1 Stack Tecnológico

| Categoría | Tecnología | Justificación |
|-----------|------------|---------------|
| Lenguaje | Python 3.11+ | Ecosistema rico en ML/AI, manipulación de datos y automatización |
| Interfaz web | Streamlit 1.56 | Prototipado rápido de dashboards interactivos con Python puro |
| IA / LLM | Azure OpenAI GPT-4o | Capacidades de comprensión y generación de código + visión multimodal |
| Embeddings | text-embedding-3-small | Balance óptimo costo/calidad para recuperación semántica (1536 dim) |
| Automatización GUI | PyAutoGUI + PyGetWindow | Control de aplicaciones sin API programática |
| Automatización Windows | pywinauto | Interacción avanzada con elementos UIA de Windows |
| Procesamiento de datos | pandas 3.0 | Manipulación eficiente de CSVs y DataFrames |
| Parsing XML | xmltodict | Conversión XML→dict pythónica para procesamiento recursivo |
| Detección de encoding | chardet | Detección automática de codificación de archivos |
| Procesamiento PDF | PyMuPDF (fitz) | Renderizado PDF→imagen de alta calidad (300 DPI) |
| Procesamiento de imagen | Pillow (PIL) | Manipulación de imágenes: recorte, máscaras alfa, conversión |
| Cálculo numérico | NumPy | Operaciones vectoriales para similitud coseno de embeddings |
| HTTP / API REST | requests | Comunicación con SharePoint REST API |
| Gestión de procesos | psutil | Control de procesos del sistema (detección, terminación) |

### 6.2 Técnicas de IA/ML por Etapa

| Etapa | Técnica | Modelo / Algoritmo | Propósito |
|-------|---------|---------------------|-----------|
| 1 | Template matching | PyAutoGUI (OpenCV) | Detección de elementos GUI independiente de resolución |
| 2 | Aplanamiento recursivo | DFS personalizado | Transformación de XML jerárquico a estructura tabular |
| 3 | Tabla de lookup | Pandas merge | Mapeo de tipos QlikView → Power BI |
| 4 | **RAG + LLM** | **text-embedding-3-small + GPT-4o** | **Traducción QVS → M Query** |
| 5 | **LLM + inferencia de tipos** | **GPT-4o + heurísticas** | **Traducción expresiones → DAX** |
| 6 | Procesamiento de imagen | PyMuPDF + PIL | Exportación PDF → PNG con metadatos espaciales |
| 7 | Integración de datos | Pandas multi-join | Síntesis multi-fuente a JSON enriquecido |
| 8 | **Feature engineering + scoring multi-criterio** | **Min-max normalisation + weighted aggregation** | **Análisis de complejidad de migración** |

---

## 7. Resultados y Discusión

### 7.1 Caso de Estudio: Airline Operations

Se aplicó el pipeline completo al reporte de demostración "Solution_Chapter 3_Airline Operations" de QlikView, que contiene:

- **2 hojas** (Main, Dashboard)
- **22 objetos visuales** (charts, listboxes, text objects, sheet objects)
- **1 script de carga** con múltiples fuentes de datos
- **Múltiples expresiones** con funciones de agregación y set analysis

**Resultados por etapa:**

| Etapa | Artefactos Generados | Observaciones |
|-------|---------------------|---------------|
| 1. Metadata | 8 CSVs + 22 XMLs + 1 QVS | Extracción completa sin intervención manual |
| 2. XML Parse | 22 CSVs aplanados | 100% de objetos procesados |
| 3. Mapping | 22 CSVs mapeados y pivotados | Todos los tipos reconocidos por la tabla |
| 4. M Query | N tablas M Query | Traducciones coherentes con patrones RAG |
| 5. DAX | Expresiones con DAX | Modelo semántico correctamente inferido |
| 6. PDF | 2 PNGs de páginas | Recorte y metadatos espaciales correctos |
| 7. Síntesis | 3 JSONs enriquecidos | Integración completa de todas las fuentes |
| 8. Complejidad | Score 22.9/100 (Low) | 27 features, 4 dimensiones, clasificación correcta |

### 7.2 Calidad de las Traducciones

**Traducción QVS → M Query (RAG):**

La incorporación de ejemplos de dominio mediante RAG mejora significativamente la calidad de las traducciones en comparación con la generación zero-shot. Los beneficios observados incluyen:

- Uso correcto de conectores M Query (`Sql.Database`, `Excel.Workbook`, `Csv.Document`) según el tipo de fuente en el QVS original.
- Traducción adecuada de constructos sin equivalente directo, como `RESIDENT` (→ referencia a tabla existente) y `CONCATENATE` (→ `Table.Combine`).
- Preservación de la lógica de transformación (filtros, cálculos, renombramientos).

**Traducción de Expresiones → DAX:**

La inyección del modelo semántico como contexto permite al LLM:

- Identificar correctamente las tablas y campos referenciados en la expresión.
- Generar funciones DAX semánticamente equivalentes (e.g., `Sum([Revenue])` → `SUMX(FactSales, FactSales[Revenue])`).
- Detectar y señalar expresiones ambiguas o de baja confianza para revisión manual.

### 7.3 Rendimiento

| Métrica | Valor |
|---------|-------|
| Tiempo de extracción de metadatos | ~2-5 min por archivo `.qvw` |
| Tiempo de parsing XML | < 10 seg por reporte |
| Tiempo de traducción M Query | ~30-60 seg por tab de script |
| Tiempo de traducción DAX | ~2-5 seg por expresión |
| Tiempo total del pipeline | ~10-15 min por reporte típico |
| Tiempo manual estimado equivalente | ~2-5 días por reporte |

### 7.4 Limitaciones

1. **Dependencia de GUI:** La etapa de extracción requiere una instalación local de QlikView con DocumentAnalyzer, limitando la escalabilidad horizontal.
2. **Calidad de traducción variable:** Expresiones complejas con set analysis anidado pueden requerir revisión manual.
3. **Recreación visual:** El sistema genera los artefactos necesarios pero no recrea automáticamente las visualizaciones en Power BI Desktop.
4. **Fragilidad GUI:** Cambios en la interfaz de QlikView o resoluciones no estándar pueden requerir actualización de las imágenes de template matching.

---

## 8. Conclusiones

### 8.1 Contribuciones

Este trabajo presenta las siguientes contribuciones:

1. **Aplicación práctica de RAG para traducción de código de dominio específico:** Se demuestra que la generación aumentada por recuperación mejora la calidad de traducción de lenguajes de BI especializados, un dominio insuficientemente representado en los datos de entrenamiento de los LLMs.

2. **Pipeline de migración end-to-end:** Se implementa un sistema completo que cubre desde la extracción de metadatos propietarios hasta la generación de artefactos listos para Power BI, reduciendo un proceso de días a minutos.

3. **Inferencia de modelo semántico para traducción contextual:** La extracción automática de tipos, relaciones y esquema de datos desde los metadatos QlikView proporciona contexto crítico que previene traducciones DAX sintácticamente correctas pero semánticamente incorrectas.

4. **Diseño de pipeline con degradación graceful:** La arquitectura permite obtener resultados parciales útiles sin requerir la ejecución exitosa de todas las etapas, un patrón valioso para pipelines de procesamiento de datos del mundo real.

5. **Análisis cuantitativo de complejidad de migración:** Se implementa un sistema de feature engineering y scoring multi-criterio que extrae 27 features de 7 fuentes de datos, las normaliza con rangos de referencia de dominio y produce un índice de complejidad ponderado. Este enfoque sigue la tradición de métricas de complejidad de software (McCabe, Halstead) adaptada al dominio de migración de BI, proporcionando una herramienta objetiva de estimación de esfuerzo y priorización.

### 8.2 Trabajo Futuro

- **Integración con Power BI REST API:** Automatizar la creación de visualizaciones en Power BI Desktop a partir de los JSONs enriquecidos.
- **Fine-tuning de modelos:** Entrenar un modelo especializado en traducción QVS→M Query con los pares generados y validados por el pipeline.
- **Extensión a otros orígenes:** Adaptar el pipeline para migración desde Tableau, SAP BusinessObjects o SSRS.
- **Métricas de calidad automatizadas:** Implementar ejecución de queries M Query y DAX generados contra datasets de prueba para validación funcional automatizada.
- **Escalabilidad:** Reemplazar la automatización GUI por parsing directo del formato binario `.qvw` si se logra ingeniería inversa del formato.

---

## Referencias

- Chen, M., et al. (2021). Evaluating Large Language Models Trained on Code. *arXiv preprint arXiv:2107.03374*.
- Gartner (2024). Magic Quadrant for Analytics and Business Intelligence Platforms.
- Halstead, M. H. (1977). *Elements of Software Science*. Elsevier.
- Kimball, R., & Ross, M. (2013). *The Data Warehouse Toolkit: The Definitive Guide to Dimensional Modeling*. Wiley.
- Lewis, P., et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *Advances in Neural Information Processing Systems*, 33, 9459-9474.
- McCabe, T. J. (1976). A Complexity Measure. *IEEE Transactions on Software Engineering*, SE-2(4), 308-320.
- OpenAI (2023). GPT-4 Technical Report. *arXiv preprint arXiv:2303.08774*.
- OpenAI (2024). GPT-4o: Multimodal Model with Vision and Audio Capabilities.
- Sweigart, A. (2019). *Automate the Boring Stuff with Python*. No Starch Press.
- Vaswani, A., et al. (2017). Attention Is All You Need. *Advances in Neural Information Processing Systems*, 30.

---

## Anexos

### Anexo A: Ejemplo de Traducción QVS → M Query

**Entrada (QlikView Script):**
```sql
///$tab Main
SET ThousandSep=',';
SET DecimalSep='.';

Flights:
LOAD
    FlightID,
    AirlineCode,
    Origin,
    Destination,
    FlightDate,
    Revenue
FROM [lib://DataSource/flights.qvd] (qvd);

Calendar:
LOAD
    Date,
    Year(Date) as Year,
    Month(Date) as Month,
    Day(Date) as Day
AUTOGENERATE 365;
```

**Salida generada (M Query):**
```
let
    Source = Qvd.Document("flights.qvd"),
    Flights = Table.SelectColumns(Source, {
        "FlightID", "AirlineCode", "Origin",
        "Destination", "FlightDate", "Revenue"
    })
in
    Flights
```

```
let
    Source = List.Dates(#date(2024,1,1), 365, #duration(1,0,0,0)),
    Calendar = Table.FromList(Source, Splitter.SplitByNothing(), {"Date"}),
    AddYear  = Table.AddColumn(Calendar, "Year", each Date.Year([Date])),
    AddMonth = Table.AddColumn(AddYear, "Month", each Date.Month([Date])),
    AddDay   = Table.AddColumn(AddMonth, "Day", each Date.Day([Date]))
in
    AddDay
```

### Anexo B: Ejemplo de Traducción de Expresión → DAX

**Entrada:**
```
Expresión QlikView: Sum({<Year={$(vCurrentYear)}>} Revenue)
Contexto: Tabla FactSales con campos [Revenue (Currency), Year (Whole Number)]
```

**Salida generada:**
```dax
Total Revenue Current Year =
CALCULATE(
    SUM(FactSales[Revenue]),
    FactSales[Year] = SELECTEDVALUE(Calendar[CurrentYear])
)
```

### Anexo C: Estructura de Archivos de Salida

```
output/
└── Solution_Chapter 3_Airline Operations/
    ├── objects.csv
    ├── objectSheets.csv
    ├── sheets.csv
    ├── expressions.csv
    ├── expressions_with_dax.csv
    ├── DAX_output.csv
    ├── fields.csv
    ├── script.qvs
    ├── m_query_output.csv
    ├── Document/
    │   ├── CH01.xml → CH01.csv → CH01_mapped_pivoted.csv
    │   ├── LB01.xml → LB01.csv → LB01_mapped_pivoted.csv
    │   └── ...
    ├── ReportPages/
    │   ├── 01_Main.png
    │   ├── 02_Dashboard.png
    │   └── page_dimensions.json
    └── Outputanalysis/
        ├── enriched_dax.json
        ├── m_query_output.json
        └── report_pages.json
```
