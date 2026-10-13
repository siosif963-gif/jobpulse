class ParserError(Exception):
    """Базовое исключение парсеров."""

    def __init__(self, message: str, error_type: str = "ERROR"):
        super().__init__(message)
        self.error_type = error_type


class SourceBlockedError(ParserError):
    """403, 429 или не-JSON ответ: источник блокирует запросы. Прерывает запуск."""

    def __init__(self, message: str, error_type: str = "BLOCKED"):
        super().__init__(message, error_type)


class SourceUnavailableError(ParserError):
    """5xx, таймаут, сетевая ошибка после исчерпания повторов."""

    def __init__(self, message: str, error_type: str = "UNAVAILABLE"):
        super().__init__(message, error_type)


class StructureChangedError(ParserError):
    """Изменилась структура JSON источника. Прерывает запуск, повтор бессмысленен."""

    def __init__(self, message: str, error_type: str = "STRUCTURE_CHANGED"):
        super().__init__(message, error_type)
