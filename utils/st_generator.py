def generate_declarations(selected_vars):
    st_code = "VAR\n"
    for v in selected_vars:
        comment = f" (* {v['comment']} *)" if v.get('comment') else ""
        st_code += f"    {v['name']} : {v['type']};{comment}\n"
    st_code += "END_VAR\n"
    return st_code

def build_prompt(selected_vars, user_request):
    """Excel mode: we provide declarations locally; ask Gemini for logic only."""
    var_list = "\n".join([f"{v['name']} ({v['type']})" for v in selected_vars])
    prompt = f"""
You are an IEC 61131-3 Structured Text (ST) code generator for PLC/DCS.
Variables available (declarations are already handled separately):
{var_list}

User request / functional description:
{user_request}

Task:
- Generate ONLY the ST LOGIC (no VAR/END_VAR declarations).
- Use ONLY the variables listed above.
- Keep code clean and standards-compliant (IEC 61131-3).
"""
    return prompt.strip()

def build_prompt_user_only(user_vars, user_request):
    """
    User-only mode: ignore Excel entirely.
    - Use ONLY 'user_vars' as known variables.
    - If more variables are needed, DECLARE NEW ONES yourself with sensible names/types.
    - Output must be COMPLETE IEC 61131-3 ST including VAR ... END_VAR + logic.
    """
    if user_vars:
        var_list = "\n".join([f"{v['name']} ({v['type']}) - {v.get('comment','')}" for v in user_vars])
    else:
        var_list = "(no predefined variables provided by the user)"

    prompt = f"""
You are an IEC 61131-3 Structured Text (ST) code generator for PLC/DCS.

Known variables defined by the USER ONLY:
{var_list}

Functional description / control logic to implement:
{user_request}

STRICT RULES:
- DO NOT use any external or hidden variables (no Excel, no prior context).
- If additional variables are needed to fulfill the logic, you MUST:
  1) Create new variable declarations with sensible names and IEC types (BOOL, INT, REAL, TIMER, etc.).
  2) Include brief comments for each new variable.
- Output MUST be a COMPLETE ST program fragment including:
  VAR
    ... variable declarations ...
  END_VAR

  ... logic statements ...

- Keep it standards-compliant and production-ready ST.
"""
    return prompt.strip()
