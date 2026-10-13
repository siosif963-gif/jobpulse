class NotFoundError(Exception):
    """Запрошенная сущность не найдена."""

    def __init__(self, message: str = "Не найдено"):
        super().__init__(message)
        self.message = message


class ParsingAlreadyRunningError(Exception):
    """Парсинг уже выполняется."""
