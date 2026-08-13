"""
    Check if the user has the required role.    
"""

def require_manager(user_role: str):
    if user_role.lower() not in {'admin', 'manager'}:
        raise PermissionError("You do not have permission to perform this action.")
    
    allowed_roles=['admin', 'manager']
    if user_role.lower() not in allowed_roles:
        raise PermissionError(f"You do not have permission to perform this action. Required roles: {', '.join(allowed_roles)}")

def require_authenticated(user_role:str):
    """
        ensure the user has a valid role to access the system.  
    """
    if not user_role or user_role.lower() not in {'admin', 'manager', 'user'}:
        raise PermissionError("You must be authenticated to perform this action.")