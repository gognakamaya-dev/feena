def B(n, category, difficulty, severity, component, description, trigger, steps, expected, actual, multi=False):
    return dict(n=n, category=category, difficulty=difficulty, severity=severity, affected_component=component,
                description=description, trigger_conditions=[trigger],
                reproduction_steps=[s.strip() for s in steps.split(">")], expected_behavior=expected,
                expected_result=expected, actual_result=actual, multi_step=multi)
