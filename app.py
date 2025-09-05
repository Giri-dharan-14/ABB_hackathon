from flask import Flask, render_template, request, jsonify, send_file
from utils.excel_parser import parse_excel
from utils.st_generator import generate_declarations, build_prompt_user_only
import google.generativeai as genai
from config import MODEL
import os
import pandas as pd
import re

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Preformatted
import textwrap
import tempfile
from datetime import datetime

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = "Uploads"
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

user_variables = []
uploaded_variables = []
last_context = []

def generate_session_report_pdf(session_data):
    """
    Generate a comprehensive PDF document for PLC code generation session
    
    session_data should contain:
    - operator_name: str
    - session_start_time: datetime
    - session_end_time: datetime
    - chat_history: list of messages
    - generated_code: dict with 'vars' and 'logic'
    - retrieved_context: list of variables
    - mode: str ('excel' or 'user')
    - clarification_summary: str
    """
    
    # Create temporary file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    
    # Create PDF document
    doc = SimpleDocTemplate(
        temp_file.name,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18
    )
    
    # Get styles and create custom styles
    styles = getSampleStyleSheet()
    custom_styles = create_custom_styles(styles)
    
    # Build document content
    story = []
    
    # Add header section
    add_pdf_header_section(story, session_data, custom_styles)
    
    # Add session overview
    add_pdf_session_overview(story, session_data, custom_styles)
    
    # Add chat history
    add_pdf_chat_history_section(story, session_data, custom_styles)
    
    # Add generated code
    add_pdf_generated_code_section(story, session_data, custom_styles)
    
    # Add retrieved context
    add_pdf_retrieved_context_section(story, session_data, custom_styles)
    
    # Add clarification summary
    add_pdf_clarification_section(story, session_data, custom_styles)
    
    # Add footer info
    add_pdf_footer_section(story, custom_styles)
    
    # Build PDF
    doc.build(story)
    
    return temp_file.name

def create_custom_styles(base_styles):
    """Create custom styles for the PDF"""
    custom_styles = {}
    
    # Title style
    custom_styles['title'] = ParagraphStyle(
        'CustomTitle',
        parent=base_styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1a365d')
    )
    
    # Heading style
    custom_styles['heading'] = ParagraphStyle(
        'CustomHeading',
        parent=base_styles['Heading2'],
        fontSize=14,
        spaceBefore=20,
        spaceAfter=12,
        textColor=colors.HexColor('#2d3748')
    )
    
    # Subheading style
    custom_styles['subheading'] = ParagraphStyle(
        'CustomSubheading',
        parent=base_styles['Heading3'],
        fontSize=12,
        spaceBefore=15,
        spaceAfter=8,
        textColor=colors.HexColor('#4a5568')
    )
    
    # Code style
    custom_styles['code'] = ParagraphStyle(
    'CodeStyle',
    parent=base_styles['Code'],
    fontSize=9,
    leftIndent=20,
    fontName='Courier',
    backColor=colors.HexColor('#f7fafc'),
    borderColor=colors.HexColor('#e2e8f0'),
    borderWidth=1,
    borderPadding=8,
    spaceBefore=6,
    spaceAfter=6,
    alignment=TA_LEFT,
    wordWrap='LTR'  # Add word wrap control
)
    
    # Normal text
    custom_styles['normal'] = ParagraphStyle(
        'CustomNormal',
        parent=base_styles['Normal'],
        fontSize=10,
        spaceAfter=6
    )
    
    # Chat styles
    custom_styles['chat_user'] = ParagraphStyle(
        'ChatUser',
        parent=base_styles['Normal'],
        fontSize=9,
        leftIndent=20,
        backColor=colors.HexColor('#e6f3ff'),
        borderColor=colors.HexColor('#3182ce'),
        borderWidth=1,
        borderPadding=5
    )
    
    custom_styles['chat_bot'] = ParagraphStyle(
        'ChatBot',
        parent=base_styles['Normal'],
        fontSize=9,
        leftIndent=20,
        backColor=colors.HexColor('#f0fff4'),
        borderColor=colors.HexColor('#38a169'),
        borderWidth=1,
        borderPadding=5
    )
    
    return custom_styles

def add_pdf_header_section(story, session_data, styles):
    """Add PDF header with title and basic info"""
    
    # Main title
    title = Paragraph('PLC Code Generation Session Report', styles['title'])
    story.append(title)
    
    # Subtitle
    subtitle = Paragraph('IEC 61131-3 Structured Text Code Generator', styles['normal'])
    subtitle.alignment = TA_CENTER
    story.append(subtitle)
    
    story.append(Spacer(1, 20))

def add_pdf_session_overview(story, session_data, styles):
    """Add session overview table"""
    
    story.append(Paragraph('Session Overview', styles['heading']))
    
    # Create overview data
    overview_data = [
        ['Parameter', 'Value'],
        ['Operator Name', session_data.get('operator_name', 'Not specified')],
        ['Session Start Time', format_datetime(session_data.get('session_start_time'))],
        ['Session End Time', format_datetime(session_data.get('session_end_time'))],
        ['Duration', calculate_duration(session_data.get('session_start_time'), 
                                      session_data.get('session_end_time'))],
        ['Generation Mode', session_data.get('mode', 'User-defined').title()],
        ['Total Chat Messages', str(len(session_data.get('chat_history', [])))],
        ['Variables Retrieved', str(len(session_data.get('retrieved_context', [])))]
    ]
    
    # Create table
    table = Table(overview_data, colWidths=[2*inch, 4*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a5568')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')])
    ]))
    
    story.append(table)
    story.append(Spacer(1, 20))

def add_pdf_chat_history_section(story, session_data, styles):
    """Add complete chat history"""
    
    story.append(Paragraph('Chat History', styles['heading']))
    
    chat_history = session_data.get('chat_history', [])
    
    if not chat_history:
        story.append(Paragraph('No chat history available.', styles['normal']))
        return
    
    # Add each message as a formatted paragraph
    for i, message in enumerate(chat_history):
        role = message.get('role', 'Unknown').capitalize()
        content = message.get('content', '')
        timestamp = message.get('timestamp', 'N/A')
        
        # Create header for each message
        msg_header = f"<b>[{timestamp}] {role}:</b>"
        story.append(Paragraph(msg_header, styles['normal']))
        
        # Choose style based on role
        msg_style = styles['chat_user'] if role.lower() == 'user' else styles['chat_bot']
        
        # Wrap long content
        wrapped_content = wrap_text(content, 80)
        story.append(Paragraph(wrapped_content, msg_style))
        story.append(Spacer(1, 8))
    
    story.append(Spacer(1, 15))

def add_pdf_generated_code_section(story, session_data, styles):
    """Add the generated code section with proper formatting"""
    
    story.append(Paragraph('Generated Code', styles['heading']))
    
    generated_code = session_data.get('generated_code', {})
    
    # Variable Declarations
    story.append(Paragraph('Variable Declarations', styles['subheading']))
    
    vars_code = generated_code.get('vars', 'No variable declarations generated.')
    if vars_code.strip():
        # Use Preformatted class for code blocks
        from reportlab.platypus import Preformatted
        
        code_style = ParagraphStyle(
            'PreformattedCode',
            parent=styles['code'],
            fontName='Courier',
            fontSize=8,
            leading=10,
            leftIndent=10,
            rightIndent=10,
            spaceBefore=6,
            spaceAfter=6
        )
        
        story.append(Preformatted(vars_code, code_style))
    else:
        story.append(Paragraph('No variable declarations generated.', styles['normal']))
    
    story.append(Spacer(1, 15))
    
    # Logic Code
    story.append(Paragraph('Logic Code', styles['subheading']))
    
    logic_code = generated_code.get('logic', 'No logic code generated.')
    if logic_code.strip():
        story.append(Preformatted(logic_code, code_style))
    else:
        story.append(Paragraph('No logic code generated.', styles['normal']))
    
    story.append(Spacer(1, 20))


def add_pdf_retrieved_context_section(story, session_data, styles):
    """Add retrieved context variables table"""
    
    story.append(Paragraph('Retrieved Context Variables', styles['heading']))
    
    context = session_data.get('retrieved_context', [])
    
    if not context:
        story.append(Paragraph('No context variables retrieved.', styles['normal']))
        return
    
    # Prepare table data
    table_data = [['Tank', 'IO Type', 'Tag Name', 'Description', 'Data Type']]
    
    for var in context:
        row = [
            var.get('tank', ''),
            var.get('io_type', ''),
            var.get('tag', ''),
            wrap_text(var.get('description', ''), 30),
            var.get('type', '')
        ]
        table_data.append(row)
    
    # Create table
    table = Table(table_data, colWidths=[0.8*inch, 1*inch, 1.2*inch, 2.2*inch, 0.8*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a5568')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP')
    ]))
    
    story.append(table)
    story.append(Spacer(1, 20))

def add_pdf_clarification_section(story, session_data, styles):
    """Add clarification summary"""
    
    story.append(Paragraph('Clarification Summary', styles['heading']))
    
    clarification = session_data.get('clarification_summary', 
                                   'No specific clarifications were recorded for this session.')
    
    # Split into paragraphs and add each
    paragraphs = clarification.split('\n\n')
    for para in paragraphs:
        if para.strip():
            wrapped_para = wrap_text(para.strip(), 100)
            story.append(Paragraph(wrapped_para, styles['normal']))
            story.append(Spacer(1, 8))

def add_pdf_footer_section(story, styles):
    """Add footer with generation timestamp"""
    
    story.append(Spacer(1, 30))
    
    # Horizontal line
    line_data = [['_' * 80]]
    line_table = Table(line_data)
    line_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 8)
    ]))
    story.append(line_table)
    
    story.append(Spacer(1, 10))
    
    # Footer text
    footer_text = f"Report generated on {datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}"
    footer_para = Paragraph(footer_text, styles['normal'])
    footer_para.alignment = TA_CENTER
    story.append(footer_para)

# Utility functions
def format_datetime(dt):
    """Format datetime object to string"""
    if dt is None:
        return 'Not recorded'
    if isinstance(dt, str):
        return dt
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def calculate_duration(start_time, end_time):
    """Calculate session duration"""
    if start_time is None or end_time is None:
        return 'Not calculated'
    
    try:
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)
        
        duration = end_time - start_time
        total_seconds = int(duration.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
            
    except Exception:
        return 'Not calculated'

def wrap_text(text, width):
    """Wrap text to specified width"""
    if not text:
        return ""
    return "<br/>".join(textwrap.wrap(str(text), width))

def escape_html(text):
    """Escape HTML characters in text"""
    if not text:
        return ""
    text = str(text)
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&#x27;')
    return text

# ------------------ ROUTES ------------------ #

@app.route("/")
def index():
    return render_template("index.html")


# ---------- Upload Excel ----------
@app.route("/api/upload_excel", methods=["POST"])
def upload_excel():
    global uploaded_variables
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    path = os.path.join(app.config["UPLOAD_FOLDER"], f.filename)
    f.save(path)
    uploaded_variables = parse_excel(path)
    return jsonify({"message": "Excel uploaded and parsed", "count": len(uploaded_variables)})


# ---------- Add user variable ----------
@app.route("/api/add_variable", methods=["POST"])
def add_variable():
    data = request.get_json()
    tank = data.get("tank", "")
    io_type = data.get("io", "")
    tag = data.get("tag", "")
    desc = data.get("description", "")

    if not tag or not io_type:
        return jsonify({"error": "Tag and IO_Type required"}), 400

    new_var = {
        "name": tag,
        "type": "BOOL" if "Digital" in io_type else "REAL",
        "comment": desc,
        "tank": tank,
        "io_type": io_type
    }
    user_variables.append(new_var)
    return jsonify({"message": "Variable added", "variable": new_var})


@app.route("/api/clear_variables", methods=["POST"])
def clear_variables():
    user_variables.clear()
    return jsonify({"message": "All user variables cleared."})


@app.route("/api/delete_variable", methods=["POST"])
def delete_variable():
    data = request.get_json()
    tag = (data.get("tag") or "").strip()
    global user_variables
    before = len(user_variables)
    user_variables = [v for v in user_variables if v["name"] != tag]
    return jsonify({"message": f"Deleted {before - len(user_variables)} variable(s)."})


# ---------- New route for deleting excel data ----------
@app.route("/api/delete_excel", methods=["POST"])
def delete_excel():
    global uploaded_variables
    uploaded_variables = []
    return jsonify({"message": "Excel data cleared."})


# ---------- Clarification Chat ----------
@app.route("/api/chat_step", methods=["POST"])
def chat_step():
    data = request.get_json()
    conversation = data.get("conversation", [])

    # Check if we have enough back-and-forth to be ready
    user_responses = len([msg for msg in conversation if msg["role"] == "user"])
    
    # After 2-3 user responses, usually we have enough info
    if user_responses >= 3:
        # Try to determine if we have enough information
        user_content = " ".join([msg["content"] for msg in conversation if msg["role"] == "user"])
        
        # Simple heuristic - if user mentioned equipment, conditions, or actions
        key_elements = ["pump", "valve", "tank", "motor", "sensor", "pressure", "temperature", "level", "flow", 
                       "start", "stop", "open", "close", "on", "off", "control", "when", "if", "trigger"]
        
        mentioned_elements = sum(1 for element in key_elements if element.lower() in user_content.lower())
        
        if mentioned_elements >= 2:  # User mentioned at least 2 key elements
            return jsonify({
                "reply": "Perfect! I have enough information to generate your control logic. Click 'Generate ST' to create the code.",
                "ready": True
            })

    clarification_prompt = """
You are a PLC control logic expert helping clarify user requirements for Structured Text code.

Conversation history:
""" + "\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation]) + """

Your goal is to ask 1-2 clarifying questions at a time to understand what the user wants.

RULES:
- Ask only plain English questions
- Focus on: what equipment, what conditions, what actions
- NEVER repeat questions already asked
- Keep responses under 50 words
- When enough info is provided, say: READY: [brief summary]

Ask what you need to know to understand the control logic.
"""
    history = [{"role": "user", "parts": [{"text": clarification_prompt}]}]  # Assuming genai format

    try:
        model = genai.GenerativeModel(MODEL)
        response = model.generate_content(history)
        raw_reply = response.text.strip()
        
        # Check if model thinks it's ready
        if "READY:" in raw_reply.upper():
            summary = raw_reply.split("READY:")[1].strip() if ":" in raw_reply else ""
            return jsonify({
                "reply": "Great! I understand your requirements. Click 'Generate ST' to create the code.",
                "ready": True,
                "summary": summary  # Added for potential use in report
            })
        
        # Filter and format response
        bot_reply = filter_and_format_questions(raw_reply, conversation)
        
        return jsonify({"reply": bot_reply, "ready": False})
        
    except Exception as e:
        return jsonify({"reply": "What equipment do you want to control?", "ready": False})

def filter_and_format_questions(text: str, conversation) -> str:
    """Filter response and avoid repeating questions"""
    if not text:
        return "What control logic do you need?"

    # Remove code patterns
    code_patterns = [r'```.*?```', r'VAR.*?END_VAR', r'\w+\s*:=.*?;']
    for pattern in code_patterns:
        text = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE)

    # Get previously asked questions to avoid repetition
    previous_questions = []
    for msg in conversation:
        if msg["role"] == "assistant" and "?" in msg["content"]:
            previous_questions.extend([q.strip() for q in msg["content"].split("?") if q.strip()])

    # Clean and format
    lines = []
    for line in text.split('\n'):
        line = line.strip()
        if len(line) < 10 or not line:
            continue
            
        # Remove numbering
        line = re.sub(r'^\d+\.?\s*', '', line)
        
        # Skip if similar question already asked
        is_duplicate = False
        for prev_q in previous_questions:
            if similarity_check(line.lower(), prev_q.lower()) > 0.7:
                is_duplicate = True
                break
                
        if not is_duplicate and len(lines) < 2:  # Max 2 questions
            if not line.endswith('?'):
                line += '?'
            lines.append(f"{len(lines) + 1}. {line}")

    if not lines:
        # Provide different fallback questions based on conversation
        fallback_questions = [
            "What specific equipment needs to be controlled?",
            "What conditions should trigger the control action?",
            "What should happen when the system activates?"
        ]
        return fallback_questions[len(conversation) % len(fallback_questions)]

    return "\n".join(lines)

def similarity_check(text1, text2):
    """Simple similarity check to avoid duplicate questions"""
    words1 = set(text1.split())
    words2 = set(text2.split())
    if not words1 or not words2:
        return 0
    return len(words1.intersection(words2)) / len(words1.union(words2))


# ---------- Enhanced Variable Matching and Creation ----------
def find_matching_variables(user_request, available_variables):
    """Find variables that match the user's request based on keywords and context"""
    matches = []
    request_lower = user_request.lower()
    
    # Keywords for different equipment types
    equipment_keywords = {
        'pump': ['pump', 'pumping'],
        'valve': ['valve', 'valves'],
        'motor': ['motor', 'motors', 'drive'],
        'sensor': ['sensor', 'sensors'],
        'level': ['level', 'levels', 'tank level'],
        'pressure': ['pressure', 'press'],
        'temperature': ['temperature', 'temp'],
        'flow': ['flow', 'flowrate'],
        'tank': ['tank', 'vessel', 'container']
    }
    
    for var in available_variables:
        var_name = var.get("name", "").lower()
        var_comment = var.get("comment", "").lower()
        var_io = var.get("io_type", "").lower()
        
        # Check if variable name or comment contains relevant keywords
        for equipment, keywords in equipment_keywords.items():
            if equipment in request_lower:
                for keyword in keywords:
                    if (keyword in var_name or keyword in var_comment or 
                        any(k in var_name for k in keywords)):
                        matches.append(var)
                        break
    
    return matches

def create_new_variable(var_name, user_request, existing_vars):
    """Create a new variable with appropriate IO type and description"""
    request_lower = user_request.lower()
    name_lower = var_name.lower()
    
    # Determine IO type based on context and naming
    io_type = "Internal"  # Default
    var_type = "BOOL"     # Default
    description = ""
    
    # Input detection patterns
    input_patterns = {
        'level': ['level', 'tank_level', 'water_level'],
        'pressure': ['pressure', 'press'],
        'temperature': ['temperature', 'temp'],
        'flow': ['flow', 'flowrate'],
        'sensor': ['sensor', 'switch', 'feedback']
    }
    
    # Output detection patterns  
    output_patterns = {
        'pump': ['pump', 'motor'],
        'valve': ['valve'],
        'heater': ['heater', 'heating'],
        'cooler': ['cooler', 'cooling'],
        'alarm': ['alarm', 'warning']
    }
    
    # Check for input variables
    for category, patterns in input_patterns.items():
        if any(pattern in name_lower for pattern in patterns):
            if category in ['level', 'pressure', 'temperature', 'flow']:
                io_type = "Analog Input"
                var_type = "REAL"
                description = f"{category.title()} measurement sensor"
            else:
                io_type = "Digital Input" 
                var_type = "BOOL"
                description = f"{category.title()} status input"
            break
    
    # Check for output variables
    if io_type == "Internal":  # Only if not already classified as input
        for category, patterns in output_patterns.items():
            if any(pattern in name_lower for pattern in patterns):
                # Check if it's analog or digital output
                if any(word in request_lower for word in ['speed', 'position', 'setpoint', 'control']):
                    io_type = "Analog Output"
                    var_type = "REAL" 
                    description = f"{category.title()} control output"
                else:
                    io_type = "Digital Output"
                    var_type = "BOOL"
                    description = f"{category.title()} control output"
                break
    
    # If still internal, try to infer from context
    if io_type == "Internal":
        if any(word in request_lower for word in ['start', 'stop', 'run', 'enable', 'trigger']):
            io_type = "Digital Output"
            description = "Control logic output"
        elif any(word in request_lower for word in ['status', 'state', 'flag', 'condition']):
            description = "Internal logic flag"
        else:
            description = "Internal variable"
    
    # Create variable dictionary
    new_var = {
        "name": var_name,
        "type": var_type,
        "comment": description,
        "tank": "",  # Could be extracted from context if needed
        "io_type": io_type
    }
    
    return new_var

def generate_unique_tag(base_name, existing_vars):
    """Generate a unique tag name to avoid conflicts"""
    # Clean base name
    base_name = re.sub(r'[^a-zA-Z0-9_]', '_', base_name)
    base_name = base_name.strip('_')
    
    if not base_name or base_name[0].isdigit():
        base_name = "VAR_" + base_name
    
    # Check if base name is unique
    existing_names = [var.get("name", "").lower() for var in existing_vars]
    
    if base_name.lower() not in existing_names:
        return base_name
    
    # Add number suffix to make it unique
    counter = 1
    while f"{base_name}_{counter}".lower() in existing_names:
        counter += 1
    
    return f"{base_name}_{counter}"


# ---------- Enhanced Generate Function ----------
@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.json
    conversation = data.get("conversation", [])
    gen_type = data.get("genType", "ST")
    source = data.get("source", "user")

    # Collect available variables based on mode
    if source == "excel":
        available_vars = uploaded_variables.copy()
    else:
        available_vars = user_variables.copy()

    # Extract user requirements from conversation
    user_messages = [m["content"] for m in conversation if m["role"] == "user"]
    if not user_messages:
        return jsonify({"error": "No user request provided"}), 400
    
    user_request = "\n".join(user_messages)

    # Find matching existing variables
    matching_vars = find_matching_variables(user_request, available_vars)

    # Build enhanced prompt for code generation
    prompt = f"""
You are an expert PLC programmer. Generate efficient Structured Text code that uses existing variables when possible.

EXISTING VARIABLES:
{format_available_variables(available_vars)}

USER REQUEST:
{user_request}

INSTRUCTIONS:
1. FIRST: Use existing variables that match the requirements
2. ONLY create new variables if absolutely necessary
3. When creating new variables, use descriptive names like: Pump_Run, Level_Sensor, Valve_Open, etc.
4. Include only variables that are ACTUALLY USED in the logic
5. Generate clean, minimal code

REQUIRED OUTPUT FORMAT:
VAR
[only variables used in the logic - mix of existing and new if needed]
variable_name : DATA_TYPE; (* description *)
END_VAR

[structured text logic - no VAR blocks here]

Generate the code now:
"""

    try:
        model = genai.GenerativeModel(MODEL)
        response = model.generate_content(prompt)
        st_code = response.text.strip()

        # Parse the generated code
        var_declarations, logic = parse_generated_code(st_code)
        
        # Extract variables used in the code
        declared_vars = parse_st_vars(var_declarations)
        
        # Enhance variables with proper IO types and descriptions
        enhanced_vars = []
        all_existing_vars = available_vars + enhanced_vars  # For unique name checking
        
        for var in declared_vars:
            var_name = var.get("tag", "")
            
            # Check if this variable exists in our available variables
            existing_var = None
            for av in available_vars:
                if av.get("name", "").lower() == var_name.lower():
                    existing_var = av
                    break
            
            if existing_var:
                # Use existing variable info
                enhanced_var = {
                    "tag": existing_var.get("name", ""),
                    "io_type": existing_var.get("io_type", "Internal"),
                    "description": existing_var.get("comment", ""),
                    "type": existing_var.get("type", "BOOL"),
                    "tank": existing_var.get("tank", "")
                }
            else:
                # Create new variable with proper classification
                unique_name = generate_unique_tag(var_name, all_existing_vars)
                new_var = create_new_variable(unique_name, user_request, all_existing_vars)
                
                enhanced_var = {
                    "tag": new_var["name"],
                    "io_type": new_var["io_type"], 
                    "description": new_var["comment"],
                    "type": new_var["type"],
                    "tank": new_var.get("tank", "")
                }
                all_existing_vars.append(new_var)
            
            enhanced_vars.append(enhanced_var)

        # Update global context with enhanced variables
        global last_context
        last_context = enhanced_vars

        # Rebuild variable declarations with enhanced info
        enhanced_var_block = "VAR\n"
        for var in enhanced_vars:
            enhanced_var_block += f"{var['tag']} : {var['type']}; (* {var['description']} *)\n"
        enhanced_var_block += "END_VAR"

        return jsonify({
            "vars": enhanced_var_block,
            "logic": logic,
            "context": enhanced_vars,
            "mode": source
        })
        
    except Exception as e:
        return jsonify({"error": f"Generation failed: {str(e)}"}), 500


def format_available_variables(variables):
    """Format available variables for the AI prompt"""
    if not variables:
        return "No variables available - will create new ones as needed."
    
    formatted = []
    for var in variables:
        name = var.get("name", "")
        var_type = var.get("type", "")
        comment = var.get("comment", "")
        io_type = var.get("io_type", "")
        tank = var.get("tank", "")
        
        formatted.append(f"- {name} ({var_type}): {comment} [{io_type}, Tank: {tank}]")
    
    return "\n".join(formatted)


def parse_generated_code(st_code):
    """Parse generated code into variable declarations and logic sections"""
    # Find VAR...END_VAR block
    var_pattern = r'VAR\s*(.*?)\s*END_VAR'
    var_match = re.search(var_pattern, st_code, re.DOTALL | re.IGNORECASE)
    
    if var_match:
        var_content = var_match.group(1).strip()
        var_declarations = f"VAR\n{var_content}\nEND_VAR"
        
        # Everything after END_VAR is logic
        logic_start = var_match.end()
        logic = st_code[logic_start:].strip()
    else:
        # No VAR block found - treat entire content as logic
        var_declarations = "VAR\nEND_VAR"
        logic = st_code
    
    return var_declarations, logic


def parse_st_vars(var_block):
    """Extract variable information from VAR declarations"""
    vars_list = []
    if not var_block:
        return vars_list
        
    lines = var_block.split("\n")
    in_var = False
    
    for line in lines:
        line = line.strip()
        if line.upper() == "VAR":
            in_var = True
            continue
        if line.upper() == "END_VAR":
            in_var = False
            continue
        if not in_var or not line or not ":" in line:
            continue

        # Parse: name : type; (* comment *)
        match = re.match(r'(\w+)\s*:\s*(\w+)\s*;\s*(?:\(\*\s*(.*?)\s*\*\))?', line)
        if match:
            name = match.group(1)
            var_type = match.group(2)
            comment = match.group(3) if match.group(3) else ""

            vars_list.append({
                "tag": name,
                "io_type": "Internal",  # Will be enhanced later
                "description": comment,
                "type": var_type,
                "tank": ""
            })
    
    return vars_list

# ---------- Download Context ----------
@app.route("/api/download_context")
def download_context():
    global last_context
    if not last_context:
        return jsonify({"error": "No context available"}), 400

    df = pd.DataFrame(last_context)
    out_path = os.path.join(app.config['UPLOAD_FOLDER'], "retrieved_context.xlsx")
    df.to_excel(out_path, index=False)
    return send_file(out_path, as_attachment=True, download_name="retrieved_context.xlsx")


# ADD THIS NEW ROUTE HERE:
@app.route("/api/generate_report", methods=["POST"])
def generate_report():
    """Generate and download session report as PDF"""
    try:
        data = request.get_json()
        
        # Collect session data
        session_data = {
            'operator_name': data.get('operator_name', 'Anonymous'),
            'session_start_time': data.get('session_start_time'),
            'session_end_time': datetime.now(),
            'chat_history': data.get('chat_history', []),
            'generated_code': {
                'vars': data.get('generated_vars', ''),
                'logic': data.get('generated_logic', '')
            },
            'retrieved_context': data.get('retrieved_context', []),
            'mode': data.get('mode', 'user'),
            'clarification_summary': data.get('clarification_summary', 
                'The user interacted with the system to generate PLC control logic. '
                'Through iterative clarification, the system understood the requirements '
                'and generated appropriate IEC 61131-3 Structured Text code.')
        }
        
        # Generate PDF report
        report_file = generate_session_report_pdf(session_data)
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        operator = session_data['operator_name'].replace(' ', '_')
        filename = f"PLC_Session_Report_{operator}_{timestamp}.pdf"
        
        return send_file(
            report_file, 
            as_attachment=True, 
            download_name=filename,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        return jsonify({"error": f"PDF report generation failed: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True)