class MissionCompilerError(Exception):
    """Base class for MVP compiler errors."""


class SchemaValidationError(MissionCompilerError):
    """MissionSpec failed JSON Schema validation."""


class MissionValidationError(MissionCompilerError):
    """MissionSpec failed semantic validation."""


class BackendCapabilityError(MissionCompilerError):
    """MissionSpec requests a feature the backend does not support."""


class CompileError(MissionCompilerError):
    """Backend compilation failed."""
