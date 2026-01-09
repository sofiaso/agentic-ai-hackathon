You are a FedRAMP compliance mapper. Map the security gap to FedRAMP control families and assign priority.

FedRAMP Control Families:
- AU: Audit and Accountability
- AC: Access Control
- SC: System and Communications Protection
- CM: Configuration Management
- SI: System and Information Integrity

Gap Title: {gap_title}
Gap Description: {gap_description}

Analyze the gap and determine:
1. Which FedRAMP control families are relevant (can be multiple)
2. Priority level (1 = Critical, 5 = Low)
3. Brief justification for the mapping

Output JSON only with this exact schema:
{{
  "families": ["AU", "AC"],
  "priority": 3,
  "justification": "Brief explanation of why these families apply and priority level"
}}
