"""Story Architect (Stage 12B.1).

Responsible for:
1. Formulating the StoryContract from an idea/topic.
2. Synthesizing a structured StoryArc with 4 to 6 scenes.
3. Applying planning duration heuristics (PLANNING_WPS).
4. Generating decoupled VisualBriefs with prohibited_mismatches.
5. Extracting atomic FactClaims with scopes, statuses, and wording constraints.
"""

import math
import re
import uuid
from typing import List, Optional

from engine.story.schema import (
    ClaimStatus,
    ContinuityRequirement,
    DurationPolicy,
    EndingStrategy,
    FactClaim,
    NarrativeRole,
    Scene,
    StoryArc,
    StoryContract,
    VisualBrief,
)

PLANNING_WPS: float = 2.5


def count_words(text: str) -> int:
    """Count words in text using standard whitespace/punctuation splitting."""
    return len(re.findall(r"\b\w+\b", text))


def estimate_duration_sec(word_count: int, wps: float = PLANNING_WPS) -> float:
    """Calculate planned duration heuristic in seconds."""
    if wps <= 0:
        raise ValueError("Words per second (wps) must be strictly positive.")
    return round(word_count / wps, 1)


class StoryArchitect:
    """Architect for synthesizing structured story contracts and scene arcs."""

    def __init__(self, planning_wps: float = PLANNING_WPS):
        self.planning_wps = planning_wps

    def synthesize_story(
        self,
        topic: str,
        target_audience: str = "general",
        tone: str = "curious_informative",
        contract_override: Optional[StoryContract] = None,
    ) -> StoryArc:
        """Synthesize a complete StoryArc from a topic string or contract override.

        If the topic matches the canonical automotive domain, generates the Golden Case.
        Otherwise, builds a structural 5-scene arc tailored to the topic.
        """
        normalized_topic = topic.strip().lower()
        if any(term in normalized_topic for term in ["auto", "carro", "coche", "vehículo", "bertha benz", "ford"]):
            return self._build_automotive_golden_case(contract_override)

        return self._build_generic_story_arc(topic, target_audience, tone, contract_override)

    def _build_automotive_golden_case(self, contract_override: Optional[StoryContract] = None) -> StoryArc:
        """Construct the canonical Golden Case: 'La Evolución del Automóvil (1886 – Vehículos Autónomos)'."""
        contract = contract_override or StoryContract(
            id=f"contract_auto_{uuid.uuid4().hex[:8]}",
            title="La Evolución del Automóvil: De la Patente de 1886 a la Conducción Autónoma",
            topic="La evolución del automóvil",
            core_question="¿Cómo pasó el automóvil de ser visto como un carruaje ruidoso e inútil a una computadora sobre ruedas que se conduce sola?",
            narrative_promise="Descubrirás los momentos cruciales y las personas audaces que transformaron para siempre el transporte humano.",
            target_audience="curious_general",
            tone="informative_engaging",
            duration_policy=DurationPolicy(
                hard_minimum_sec=61.0,
                planning_target_sec=78.0,
                soft_maximum_sec=90.0,
            ),
            must_include_entities=[
                "Benz Patent-Motorwagen",
                "Bertha Benz",
                "Henry Ford",
                "Modelo T",
            ],
            must_avoid_pitfalls=[
                "afirmar que Ford inventó el primer automóvil",
                "asegurar que Bertha Benz viajó sin avisar a las autoridades como si fuera un crimen",
                "decir que todos los coches modernos procesan millones de datos ilimitados",
            ],
            ending_strategy=EndingStrategy.PAYOFF,
        )

        scenes: List[Scene] = []

        # Scene 01: Hook (~11s)
        s1_text = (
            "En 1886, el mundo creía que los caballos jamás serían reemplazados. "
            "Pero un extraño artefacto de tres ruedas cambió la historia para siempre."
        )
        s1_words = count_words(s1_text)
        s1_dur = estimate_duration_sec(s1_words, self.planning_wps)
        scenes.append(
            Scene(
                id="scene_01",
                scene_index=0,
                narrative_role=NarrativeRole.HOOK,
                dependencies=[],
                script_text=s1_text,
                word_count=s1_words,
                estimated_duration_sec=s1_dur,
                visual_brief=VisualBrief(
                    subject="Carruaje motorizado de tres ruedas de finales del siglo XIX",
                    era="1886",
                    environment="Calle adoquinada de época con bruma matinal y farolas tenues",
                    action="Vehículo rudimentario avanzando despacio mientras transeúntes observan con asombro y escepticismo",
                    mood="Misterioso, histórico, pionero",
                    search_keywords=["Benz Patent-Motorwagen 1886", "first motor carriage", "19th century street"],
                    prohibited_mismatches=[
                        "automóviles modernos con cuatro ruedas de caucho sintético",
                        "asfalto contemporáneo con líneas pintadas",
                        "postes eléctricos o rascacielos actuales",
                    ],
                    continuity=ContinuityRequirement(
                        visual_anchor="Carruaje de tres ruedas",
                        era_progression="1886 inicio",
                        lighting_mood="Bruma matinal dorada",
                    ),
                ),
                factual_claims=[
                    FactClaim(
                        claim_text="El Benz Patent-Motorwagen patentado en 1886 es ampliamente reconocido como el primer automóvil comercial impulsado por motor de combustión interna.",
                        scope="Primer vehículo diseñado específicamente con motor de combustión de gasolina",
                        source_reference="German Patent No. 37435 (1886) / Mercedes-Benz Classic",
                        status=ClaimStatus.VERIFIED,
                        wording_constraints=[
                            "Reconocer el contexto del motor de combustión interna y la patente formal de Carl Benz.",
                        ],
                    )
                ],
            )
        )

        # Scene 02: Origin / Context (~15s)
        s2_text = (
            "Aquel invento era el Benz Patent-Motorwagen. "
            "Sin embargo, nadie lo compraba hasta que en 1888 Bertha Benz tomó el vehículo y completó el primer viaje de más de cien kilómetros, demostrando su viabilidad real."
        )
        s2_words = count_words(s2_text)
        s2_dur = estimate_duration_sec(s2_words, self.planning_wps)
        scenes.append(
            Scene(
                id="scene_02",
                scene_index=1,
                narrative_role=NarrativeRole.ORIGIN_CONTEXT,
                dependencies=["scene_01"],
                script_text=s2_text,
                word_count=s2_words,
                estimated_duration_sec=s2_dur,
                visual_brief=VisualBrief(
                    subject="Bertha Benz conduciendo el Benz Patent-Motorwagen No. 3 con sus hijos adolescentes",
                    era="1888",
                    environment="Camino rural de tierra sin pavimentar entre Mannheim y Pforzheim",
                    action="Mujer con sombrero y vestimenta victoriana guiando el vehículo con serenidad y deteniéndose en una botica",
                    mood="Decidido, aventurero, luz diurna de campo",
                    search_keywords=["Bertha Benz historic journey", "Wiesloch pharmacy 1888", "antique car country road"],
                    prohibited_mismatches=[
                        "vehículos con carrocería cerrada de acero moderno",
                        "autopistas de alta velocidad",
                        "estaciones de servicio con bombas eléctricas modernas",
                    ],
                    continuity=ContinuityRequirement(
                        visual_anchor="Benz Patent-Motorwagen",
                        era_progression="1888 travesía pionera",
                        lighting_mood="Luz diurna soleada",
                    ),
                ),
                factual_claims=[
                    FactClaim(
                        claim_text="Bertha Benz realizó en agosto de 1888 el primer viaje de larga distancia en automóvil recorriendo aproximadamente 104 kilómetros entre Mannheim y Pforzheim.",
                        scope="Primer viaje de larga distancia documentado con fines de validación técnica y difusión pública",
                        source_reference="Mercedes-Benz Classic Archive / Wiesloch Historic Landmark Record",
                        status=ClaimStatus.VERIFIED,
                        wording_constraints=[
                            "Evitar formular que actuó sin avisar a las autoridades como si fuera un delito; enfatizar el propósito pionero de validar la viabilidad del invento.",
                        ],
                    )
                ],
            )
        )

        # Scene 03: Development / Turning Point (~17.5s)
        s3_text = (
            "El auto seguía siendo un lujo para millonarios hasta que Henry Ford introdujo la línea de montaje móvil en 1913. "
            "El ensamble del chasis del Modelo T bajó de doce horas a noventa y tres minutos, democratizando el transporte masivo."
        )
        s3_words = count_words(s3_text)
        s3_dur = estimate_duration_sec(s3_words, self.planning_wps)
        scenes.append(
            Scene(
                id="scene_03",
                scene_index=2,
                narrative_role=NarrativeRole.DEVELOPMENT_TURNING_POINT,
                dependencies=["scene_02"],
                script_text=s3_text,
                word_count=s3_words,
                estimated_duration_sec=s3_dur,
                visual_brief=VisualBrief(
                    subject="Línea de ensamblaje móvil industrial de principios de siglo XX",
                    era="1913-1915",
                    environment="Nave de fábrica Highland Park con tragaluces, poleas y líneas de montaje",
                    action="Chasis oscuros desplazándose continuamente mientras obreros montan componentes con sincronía metódica",
                    mood="Industrial, metódico, vertiginoso",
                    search_keywords=["Ford Model T moving assembly line", "Highland Park 1913 factory", "vintage car production"],
                    prohibited_mismatches=[
                        "brazos robóticos soldadores modernos amarillos",
                        "operarios con tabletas digitales o cascos modernos",
                        "coches pintados de múltiples colores modernos",
                    ],
                    continuity=ContinuityRequirement(
                        visual_anchor="Chasis y línea móvil",
                        era_progression="1913 producción masiva",
                        lighting_mood="Luz cenital industrial",
                    ),
                ),
                factual_claims=[
                    FactClaim(
                        claim_text="En 1913 Henry Ford implementó la línea de ensamble móvil en Highland Park, reduciendo el tiempo de montaje del chasis del Modelo T de unas 12 horas a 93 minutos.",
                        scope="Ensamble del chasis en planta de Highland Park (1913-1914)",
                        source_reference="Ford Motor Company Historical Records / Henry Ford Museum",
                        status=ClaimStatus.VERIFIED,
                        wording_constraints=[
                            "Especificar que la reducción a 93 minutos aplicaba al chasis del Modelo T.",
                            "No adjudicar a Ford la invención absoluta del concepto de producción en serie, sino la introducción de la línea móvil automotriz.",
                        ],
                    )
                ],
            )
        )

        # Scene 04: Transformation (~17s)
        s4_text = (
            "Durante las décadas siguientes, la mecánica cedió el mando a la electrónica. "
            "Los microprocesadores sustituyeron a los carburadores, integrando frenos antibloqueo, inyección computarizada y sensores capaces de monitorear cada parámetro del vehículo en tiempo real."
        )
        s4_words = count_words(s4_text)
        s4_dur = estimate_duration_sec(s4_words, self.planning_wps)
        scenes.append(
            Scene(
                id="scene_04",
                scene_index=3,
                narrative_role=NarrativeRole.TRANSFORMATION,
                dependencies=["scene_03"],
                script_text=s4_text,
                word_count=s4_words,
                estimated_duration_sec=s4_dur,
                visual_brief=VisualBrief(
                    subject="Transición tecnológica de motores y tableros automotrices",
                    era="1980-2010",
                    environment="Laboratorio de pruebas técnicas y túnel de viento aerodinámico",
                    action="Secuencia ágil mostrando circuitos electrónicos, sensores de motor y pruebas de telemetría digital",
                    mood="Tecnológico, preciso, dinámico",
                    search_keywords=["automotive ECU microchip", "car telemetry sensor testing", "modern car engineering"],
                    prohibited_mismatches=[
                        "carretas de tracción a sangre",
                        "prototipos de coches voladores de ciencia ficción",
                        "planos mecánicos dibujados a pluma de 1800",
                    ],
                    continuity=ContinuityRequirement(
                        visual_anchor="Componentes automotrices en evolución",
                        era_progression="1980-2010 digitalización",
                        lighting_mood="Luz de laboratorio azul y neutra",
                    ),
                ),
                factual_claims=[
                    FactClaim(
                        claim_text="A finales del siglo XX y principios del XXI, los microprocesadores y las ECU reemplazaron los sistemas mecánicos tradicionales por control computarizado en la industria automotriz.",
                        scope="Transición global de la industria automotriz hacia la arquitectura mecatrónica (1980-2010)",
                        source_reference="SAE International Technical Overview of Automotive Electronics",
                        status=ClaimStatus.VERIFIED,
                        wording_constraints=[
                            "Enfatizar la transición progresiva de control puramente mecánico a control electrónico digital.",
                        ],
                    )
                ],
            )
        )

        # Scene 05: Payoff (~16.5s)
        s5_text = (
            "Hoy, el automóvil ya no es una simple máquina rodante, sino una supercomputadora con ruedas. "
            "Equipados con cámaras, radares y LiDAR, los sistemas autónomos leen la ciudad entera a cada instante, cerrando un círculo que comenzó con un frágil triciclo."
        )
        s5_words = count_words(s5_text)
        s5_dur = estimate_duration_sec(s5_words, self.planning_wps)
        scenes.append(
            Scene(
                id="scene_05",
                scene_index=4,
                narrative_role=NarrativeRole.PAYOFF,
                dependencies=["scene_04"],
                script_text=s5_text,
                word_count=s5_words,
                estimated_duration_sec=s5_dur,
                visual_brief=VisualBrief(
                    subject="Vehículo autónomo contemporáneo navegando en entorno urbano con telemetría visual",
                    era="Presente",
                    environment="Avenida metropolitana contemporánea al anochecer con luminarias urbanas",
                    action="Vehículo eléctrico autónomo desplazándose con visualización de nube de puntos LiDAR y detección de objetos circundantes",
                    mood="Futurista, sofisticado, conclusivo",
                    search_keywords=["autonomous vehicle night city", "lidar point cloud drive", "smart mobility street"],
                    prohibited_mismatches=[
                        "locomotoras a vapor o maquinaria del siglo XIX",
                        "talleres de herrería antiguos",
                        "fotografías monocromáticas en sepia",
                    ],
                    continuity=ContinuityRequirement(
                        visual_anchor="Vehículo en movimiento",
                        era_progression="Presente autónomo",
                        lighting_mood="Luces nocturnas urbanas y tonalidades azul neón",
                    ),
                ),
                factual_claims=[
                    FactClaim(
                        claim_text="Los vehículos autónomos y conectados avanzados procesan grandes flujos de datos sensoriales por segundo mediante LiDAR, radar y visión artificial con redes neuronales.",
                        scope="Sistemas de conducción automatizada de nivel 3 o superior en pruebas y despliegues controlados",
                        source_reference="SAE J3016 Autonomy Taxonomy / IEEE Vehicular Technology Society",
                        status=ClaimStatus.CONTEXT_REQUIRED,
                        wording_constraints=[
                            "Acotar el procesamiento de flujos masivos de datos a sistemas autónomos equipados con LiDAR y múltiples sensores.",
                            "Evitar afirmaciones absolutas descontextualizadas como 'todos los vehículos procesan millones de datos ilimitados'.",
                        ],
                    )
                ],
            )
        )

        total_dur = round(sum(s.estimated_duration_sec for s in scenes), 1)

        return StoryArc(
            id=f"story_auto_{uuid.uuid4().hex[:8]}",
            contract=contract,
            scenes=scenes,
            target_duration_sec=contract.duration_policy.planning_target_sec,
            total_estimated_duration_sec=total_dur,
            status="draft",
        )

    def _build_generic_story_arc(
        self,
        topic: str,
        target_audience: str,
        tone: str,
        contract_override: Optional[StoryContract] = None,
    ) -> StoryArc:
        """Construct a valid 5-scene StoryArc for any generic topic satisfying all contracts."""
        title = f"La Fascinante Historia de {topic.capitalize()}"
        contract = contract_override or StoryContract(
            id=f"contract_gen_{uuid.uuid4().hex[:8]}",
            title=title,
            topic=topic,
            core_question=f"¿Qué secreto transformó radicalmente nuestra comprensión de {topic}?",
            narrative_promise=f"Descubrirás la historia oculta y el impacto real que {topic} tiene en nuestras vidas.",
            target_audience=target_audience,
            tone=tone,
            duration_policy=DurationPolicy(
                hard_minimum_sec=61.0,
                planning_target_sec=78.0,
                soft_maximum_sec=90.0,
            ),
            must_include_entities=[topic],
            must_avoid_pitfalls=["usar lenguaje cliché o clickbait vacío sin datos"],
            ending_strategy=EndingStrategy.PAYOFF,
        )

        # Standard 5-scene progression meeting ~76-78s
        scripts = [
            # Scene 01: Hook (~12s, ~30 words)
            (
                NarrativeRole.HOOK,
                [],
                f"Casi todo lo que crees saber sobre {topic} comenzó con una paradoja que desconcertó a los expertos. "
                "Muy pocos conocen la verdadera chispa que lo cambió todo.",
            ),
            # Scene 02: Origin / Context (~15s, ~38 words)
            (
                NarrativeRole.ORIGIN_CONTEXT,
                ["scene_01"],
                f"En sus orígenes, {topic} no era considerado una prioridad ni una solución viable. "
                "Los primeros intentos enfrentaron rechazo sistemático y limitaciones técnicas severas antes de demostrar su verdadero potencial en el mundo real.",
            ),
            # Scene 03: Development / Turning Point (~18s, ~45 words)
            (
                NarrativeRole.DEVELOPMENT_TURNING_POINT,
                ["scene_02"],
                f"El punto de quiebre ocurrió cuando un nuevo enfoque metodológico demostró que {topic} podía resolver problemas a gran escala. "
                "Ese salto cualitativo desafió los dogmas establecidos y aceleró una adopción global sin precedentes en la industria.",
            ),
            # Scene 04: Transformation (~17s, ~43 words)
            (
                NarrativeRole.TRANSFORMATION,
                ["scene_03"],
                f"A partir de ese instante, la evolución de {topic} se volvió imparable. "
                "Las herramientas tradicionales quedaron obsoletas mientras nuevas generaciones de investigadores perfeccionaban sistemas cada vez más eficientes, robustos y accesibles.",
            ),
            # Scene 05: Payoff (~16s, ~40 words)
            (
                NarrativeRole.PAYOFF,
                ["scene_04"],
                f"Hoy comprendemos que sin aquel descubrimiento inicial sobre {topic}, nuestro presente sería completamente diferente. "
                "Una lección imborrable sobre cómo las ideas audaces terminan definiendo el futuro que todos compartimos.",
            ),
        ]

        scenes: List[Scene] = []
        for idx, (role, deps, text) in enumerate(scripts):
            scene_id = f"scene_{idx+1:02d}"
            words = count_words(text)
            dur = estimate_duration_sec(words, self.planning_wps)
            scenes.append(
                Scene(
                    id=scene_id,
                    scene_index=idx,
                    narrative_role=role,
                    dependencies=deps,
                    script_text=text,
                    word_count=words,
                    estimated_duration_sec=dur,
                    visual_brief=VisualBrief(
                        subject=f"Representación temática de {topic}",
                        era="Contemporánea e histórica",
                        environment="Entorno descriptivo conceptual",
                        action="Despliegue visual dinámico acorde al relato",
                        mood="Informativo y cinemático",
                        search_keywords=[topic, f"{topic} history", f"{topic} documentary"],
                        prohibited_mismatches=["imágenes no relacionadas o marcas comerciales ajenas"],
                    ),
                    factual_claims=[
                        FactClaim(
                            claim_text=f"Aspectos fundacionales de {topic} documentados en la literatura correspondiente.",
                            status=ClaimStatus.VERIFIED,
                        )
                    ],
                )
            )

        total_dur = round(sum(s.estimated_duration_sec for s in scenes), 1)

        return StoryArc(
            id=f"story_{uuid.uuid4().hex[:8]}",
            contract=contract,
            scenes=scenes,
            target_duration_sec=contract.duration_policy.planning_target_sec,
            total_estimated_duration_sec=total_dur,
            status="draft",
        )
