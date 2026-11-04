"""Deterministic Knowledge Bank of verified, high-retention facts for offline editorial generation."""

from dataclasses import dataclass
from typing import Dict, List, Optional
import re


@dataclass(frozen=True)
class FactCapsule:
    """A verified factual capsule ready for structured short-form scripting."""

    id: str
    domain: str
    topic: str
    keywords: List[str]
    hook_question: str
    hook_statement: str
    hook_surprise: str
    body_segment_1: str
    body_segment_2: str
    cta: str
    source_note: str


FACT_CATALOG: List[FactCapsule] = [
    FactCapsule(
        id="tech_01_bug_hopper",
        domain="tecnologia",
        topic="El primer bug informático",
        keywords=["tecnologia", "tecnología", "computacion", "computación", "programacion", "programación", "software", "bug", "codigo", "código", "ordenador", "computadora"],
        hook_question="¿Sabías que el primer bug informático de la historia fue literalmente un insecto real?",
        hook_statement="El origen de la palabra bug en informática no proviene de un error de código.",
        hook_surprise="Todo lo que creías sobre el origen de los errores informáticos está completamente equivocado.",
        body_segment_1="En 1947, los ingenieros del superordenador Mark II hallaron una polilla viva atrapada en un relé.",
        body_segment_2="La pionera Grace Hopper pegó el insecto en el libro de registro como el primer caso real de bug.",
        cta="¿Conocías esta curiosidad histórica? Sígueme para más historias.",
        source_note="Registro del Museo Smithsonian del Harvard Mark II (9 de septiembre de 1947).",
    ),
    FactCapsule(
        id="tech_02_webcam_coffee",
        domain="tecnologia",
        topic="La primera webcam del mundo",
        keywords=["webcam", "camara", "cámara", "internet", "cafe", "café", "inventos", "curiosidades"],
        hook_question="¿Sabías que la primera cámara web de la historia se inventó exclusivamente para vigilar café?",
        hook_statement="La tecnología de videollamadas que usamos hoy nació por culpa de una cafetera vacía.",
        hook_surprise="El invento de la webcam no surgió por seguridad militar sino por pura pereza universitaria.",
        body_segment_1="En 1991, investigadores de Cambridge instalaron una cámara conectada a su red local hacia una cafetera.",
        body_segment_2="Así evitaban bajar tres pisos para comprobar si quedaba café caliente antes de levantarse de su escritorio.",
        cta="Increíble cómo nacen las grandes tecnologías. Sígueme para más.",
        source_note="The Trojan Room Coffee Pot, Universidad de Cambridge.",
    ),
    FactCapsule(
        id="tech_03_first_internet_message",
        domain="tecnologia",
        topic="El primer mensaje de Internet",
        keywords=["internet", "red", "arpanet", "mensaje", "primer", "historia de internet", "web"],
        hook_question="¿Sabías cuál fue la primera palabra jamás transmitida por Internet antes de colapsar?",
        hook_statement="El primer mensaje de la historia de Internet fue un accidente incompleto.",
        hook_surprise="La red que conecta al planeta entero comenzó con un colapso en su segunda letra.",
        body_segment_1="En octubre de 1969, dos universidades intentaron enviar la palabra LOGIN a través de la red ARPANET.",
        body_segment_2="El sistema colapsó tras enviar únicamente la L y la O, convirtiendo 'LO' en el primer mensaje.",
        cta="Así empezó la era digital. Sígueme para más secretos de la red.",
        source_note="Registro del enlace UCLA-Stanford en ARPANET (29 de octubre de 1969).",
    ),
    FactCapsule(
        id="space_01_moon_footprints",
        domain="espacio",
        topic="Las huellas en la Luna",
        keywords=["luna", "espacio", "astronauta", "apolo", "huellas", "astronomia", "astronomía", "cosmos"],
        hook_question="¿Sabías que las huellas de los astronautas en la Luna durarán millones de años intactas?",
        hook_statement="Las pisadas del programa Apolo permanecerán en la superficie lunar mucho más que la humanidad.",
        hook_surprise="Nada en la Tierra dura tanto tiempo como una simple pisada humana en la Luna.",
        body_segment_1="Al no existir atmósfera en la Luna, no hay viento, lluvia ni erosión hídrica que borre el terreno.",
        body_segment_2="Solo el impacto esporádico de micrometeoritos degradará lentamente las huellas tras millones de años.",
        cta="El espacio preserva nuestra historia. Sígueme para más datos cósmicos.",
        source_note="NASA Lunar Science Data.",
    ),
    FactCapsule(
        id="science_01_mpemba_effect",
        domain="ciencia",
        topic="El efecto Mpemba",
        keywords=["ciencia", "fisica", "física", "agua", "hielo", "temperatura", "experimento", "misterio"],
        hook_question="¿Sabías que bajo ciertas condiciones el agua caliente se congela más rápido que la fría?",
        hook_statement="La física del agua esconde una paradoja contraintuitiva comprobada en laboratorios.",
        hook_surprise="Todo lo que la lógica nos dicta sobre enfriar agua se contradice con el efecto Mpemba.",
        body_segment_1="Un estudiante tanzano descubrió en 1963 que su mezcla tibia de helado se congelaba antes que las frías.",
        body_segment_2="La evaporación rápida y los enlaces de hidrógeno explican este fenómeno que desafía la intuición.",
        cta="La ciencia siempre desafía lo evidente. Sígueme para más curiosidades.",
        source_note="Mpemba & Osborne, Physics Education (1969).",
    ),
    FactCapsule(
        id="space_02_mars_rovers",
        domain="espacio",
        topic="La exploración de Marte",
        keywords=["marte", "planeta rojo", "rover", "curiosity", "perseverance"],
        hook_question="¿Sabías que en Marte un robot celebró su cumpleaños cantándose a sí mismo?",
        hook_statement="La exploración de Marte esconde momentos conmovedores protagonizados por robots solitarios.",
        hook_surprise="Todo lo que imaginabas sobre la exploración de Marte cambia al conocer a Curiosity.",
        body_segment_1="En 2013, el rover Curiosity programó sus motores para emitir vibraciones acústicas.",
        body_segment_2="Así cantó la melodía del Feliz Cumpleaños en la más absoluta soledad de Marte.",
        cta="La exploración espacial nunca deja de conmovernos. Sígueme para más.",
        source_note="NASA Jet Propulsion Laboratory, Curiosity Rover Mission.",
    ),
    FactCapsule(
        id="tech_04_gps_relativity",
        domain="tecnologia",
        topic="El GPS y la relatividad de Einstein",
        keywords=["gps", "satelite", "satélite", "ubicacion", "ubicación", "mapas", "relatividad", "einstein", "tiempo"],
        hook_question="¿Sabías que el GPS de tu celular fallaría por kilómetros sin la teoría de Einstein?",
        hook_statement="El sistema GPS depende de correcciones diarias basadas en la relatividad general.",
        hook_surprise="Tu mapa del teléfono se descalibraría diez kilómetros al día si ignoráramos a Einstein.",
        body_segment_1="Los relojes atómicos en los satélites GPS avanzan 38 microsegundos más rápido cada día debido a la menor gravedad orbital.",
        body_segment_2="Los ingenieros ajustan matemáticamente esa diferencia temporal para que tu ubicación no se desvíe.",
        cta="La física teórica guía tu camino diario. Sígueme para más secretos de la ciencia.",
        source_note="Ashby, N. Relativity in the Global Positioning System, Living Rev. Relativity (2003).",
    ),
    FactCapsule(
        id="tech_05_smartphone_heat",
        domain="tecnologia",
        topic="Por qué los celulares se calientan",
        keywords=["celular", "celulares", "movil", "móvil", "calientan", "calienta", "calor", "juegas", "juegos", "bateria", "batería", "procesador"],
        hook_question="¿Sabías por qué tu celular se calienta tanto exactamente cuando abres un juego pesado?",
        hook_statement="El calor en tu teléfono no es un fallo, sino un mecanismo de protección de sus microchips.",
        hook_surprise="Tu celular prefiere perder velocidad antes que quemar sus circuitos internos.",
        body_segment_1="Los procesadores móviles carecen de ventiladores activos y disipan energía en forma de calor puro.",
        body_segment_2="Para evitar fundirse, activan el estrangulamiento térmico y reducen automáticamente su potencia.",
        cta="La microelectrónica cuidando tu bolsillo. Sígueme para entender mejor tu tecnología.",
        source_note="IEEE Micro: Thermal Management and Throttling in Mobile SoCs.",
    ),
    FactCapsule(
        id="tech_06_turing_ai",
        domain="tecnologia",
        topic="El origen de la inteligencia artificial",
        keywords=["inteligencia artificial", "ia", "ai", "turing", "robot", "algoritmo", "chatgpt"],
        hook_question="¿Sabías que la pregunta fundamental sobre la inteligencia artificial fue formulada hace más de 70 años?",
        hook_statement="Alan Turing predijo los debates sobre inteligencia artificial mucho antes de que existieran computadoras comerciales.",
        hook_surprise="Todo lo que discutimos hoy sobre máquinas pensantes comenzó con un juego de salón victoriano.",
        body_segment_1="En 1950, Alan Turing publicó su célebre prueba de imitación para evaluar si una máquina puede pensar.",
        body_segment_2="Su visión estableció las bases teóricas de todos los modelos y algoritmos que hoy llamamos IA.",
        cta="El futuro se escribió en el pasado. Sígueme para más hitos tecnológicos.",
        source_note="Alan Turing, Computing Machinery and Intelligence, Mind (1950).",
    ),
    FactCapsule(
        id="tech_07_apple_pricing",
        domain="tecnologia",
        topic="El precio del primer ordenador Apple",
        keywords=["apple", "steve jobs", "wozniak", "mac", "iphone", "apple 1", "apple-1", "precio"],
        hook_question="¿Sabías por qué el primer ordenador de Apple se vendió exactamente a 666 dólares con 66 centavos?",
        hook_statement="El precio del primer ordenador de Apple no tenía relación con supersticiones sino con números repetidos.",
        hook_surprise="El ordenador que fundó el imperio de Apple costaba una cifra que muchos consideraron diabólica.",
        body_segment_1="Steve Wozniak fijó el precio mayorista en 500 dólares y añadió un tercio de margen para las tiendas.",
        body_segment_2="A Wozniak simplemente le gustaba ver dígitos repetidos al teclear en las calculadoras de la época.",
        cta="Detalles curiosos detrás de los gigantes de la tecnología. Sígueme para más.",
        source_note="Steve Wozniak, Autobiografía iWoz (2006).",
    ),
    FactCapsule(
        id="history_01_cleopatra_moon",
        domain="historia",
        topic="Cleopatra y la llegada a la Luna",
        keywords=["historia", "histórica", "historica", "histórico", "historico", "tiempo", "cleopatra", "egipto", "piramides", "pirámides", "antiguo", "cronologia", "cronología", "humanidad", "humana"],
        hook_question="¿Sabías que Cleopatra vivió más cerca de la llegada a la Luna que de la Gran Pirámide?",
        hook_statement="Nuestra percepción de la línea temporal de la historia humana está profundamente distorsionada.",
        hook_surprise="La distancia temporal entre Cleopatra y el primer teléfono inteligente te volará la cabeza.",
        body_segment_1="Las pirámides de Guiza se construyeron hacia el 2500 antes de Cristo, dos milenios antes de Cleopatra.",
        body_segment_2="Cleopatra reinó en el año 30 antes de Cristo, a menos de dos mil años de la misión Apolo 11.",
        cta="El tiempo es más fascinante de lo que creemos. Sígueme para más.",
        source_note="Cronología histórica de las dinastías del Antiguo Egipto.",
    ),
]


class KnowledgeNotFoundError(Exception):
    """Raised when no verified factual capsule exists for a topic in KnowledgeBank."""
    pass


class KnowledgeBank:
    """Lookup and retrieval engine for verified, bulletproof facts."""

    @classmethod
    def find_fact(
        cls,
        raw_text: str,
        domain: Optional[str] = None,
        clean_topic: Optional[str] = None,
        raise_on_missing: bool = False,
    ) -> FactCapsule:
        """Find the most relevant FactCapsule based on text keywords or domain, falling back gracefully."""
        text_lower = raw_text.lower()
        if clean_topic:
            text_lower = f"{text_lower} {clean_topic.lower()}"

        # Score matching facts
        best_match: Optional[FactCapsule] = None
        best_score = -1

        for fact in FACT_CATALOG:
            score = 0
            if domain and fact.domain == domain.lower():
                score += 5
            for kw in fact.keywords:
                # Direct match in the cleanly extracted topic has highest relevance (+6)
                if clean_topic and (re.search(r"\b" + re.escape(kw) + r"\b", clean_topic.lower()) or kw == clean_topic.lower()):
                    score += 6
                if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                    score += 3
                elif kw in text_lower:
                    score += 1
            if score > best_score:
                best_score = score
                best_match = fact

        # If a match with score >= 2 was found, return it
        if best_match and best_score >= 2:
            return best_match

        # Fail-fast: No fake canned templates ("¿Sabías que existe un hecho fascinante...")
        if raise_on_missing:
            raise KnowledgeNotFoundError(
                f"No se encontró ninguna cápsula factual verificada en KnowledgeBank para '{raw_text[:60]}'"
            )

        # Default guaranteed high-retention fact (First bug) only when explicitly non-raising
        return FACT_CATALOG[0]
