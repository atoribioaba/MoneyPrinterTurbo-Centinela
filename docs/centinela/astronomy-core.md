# EL CENTINELA DEL UNIVERSO — Astronomy Core V0.1

## Estado

FASE 2 — NÚCLEO ASTRONÓMICO

Motor:

- Astronomy Engine 2.1.19
- MIT
- OPEN SOURCE + 100 % GRATUITA
- CPU
- local
- sin llamadas de red en runtime

## Arquitectura

    fecha/hora + observador
             ↓
      AstronomyContext
             ↓
      AstronomyDirector
             ↓
         ScenePlan

El LLM no es la fuente de las efemérides.

## Capacidades

El núcleo proporciona:

- Sol;
- Luna;
- Mercurio;
- Venus;
- Marte;
- Júpiter;
- Saturno;
- Urano;
- Neptuno;
- Plutón;
- coordenadas topocéntricas;
- RA/DEC J2000;
- RA/DEC equador-de-fecha;
- azimut;
- altitud geométrica;
- altitud aparente;
- distancia topocéntrica;
- distancia geocéntrica;
- magnitud visual;
- fase;
- fracción iluminada;
- inclinación aparente de los anillos de Saturno;
- elongación solar;
- constelación;
- salida;
- puesta;
- culminación;
- crepúsculo civil;
- crepúsculo náutico;
- crepúsculo astronómico;
- fase lunar;
- libración lunar;
- diámetro angular lunar;
- perigeo;
- apogeo;
- cuartos lunares;
- equinoccios;
- solsticios;
- eclipses solares locales opcionales;
- eclipses lunares opcionales.

## Zona horaria

Se usa `zoneinfo` con `tzdata`.

Los datetimes de entrada sin zona horaria son rechazados.

No se calculan efemérides usando horas locales ambiguas.

## Rigor

Las magnitudes calculadas conservan:

- fuente;
- método;
- estado científico;
- limitaciones.

Astronomy Engine documenta un objetivo aproximado de ±1 minuto
de arco para sus cálculos posicionales soportados.

Las salidas y puestas incorporan su modelo estándar de refracción
cerca del horizonte.

Los crepúsculos -6°, -12° y -18° se calculan geométricamente,
sin aplicar refracción, conforme al contrato de SearchAltitude.

Los datos de estaciones de Astronomy Engine están validados
directamente por su suite para 1800-2100; fuera de ese intervalo
se etiquetan como aproximación divulgativa.

## Publicación

Astronomy Engine es el motor determinista local, pero no sustituye
la política científica de El Centinela.

Antes de publicar afirmaciones dependientes de efemérides actuales,
eclipses u otros acontecimientos astronómicos, la fase de dirección
deberá corroborarlas con una fuente primaria apropiada:

- NASA;
- ESA;
- IGN;
- IAU;
- observatorios;
- literatura científica.

## No incluido en esta fase

No se incorpora todavía:

- meteorología;
- seeing;
- nubosidad;
- contaminación lumínica;
- noticias;
- misiones actuales;
- descubrimientos;
- Astroquery;
- Astropy;
- catálogos de cielo profundo.

No se añade Astropy porque Astronomy Engine cubre el núcleo actual
con menor coste de instalación y cero dependencias externas propias.

Astropy se incorporará sólo si una fase real necesita FITS, WCS,
unidades físicas avanzadas o transformaciones que justifiquen su peso.

## API

    GET /api/v1/astronomy/health

    POST /api/v1/astronomy/context

La WebUI se conectará en Fase 3 junto con AstronomyDirector y ScenePlan.
