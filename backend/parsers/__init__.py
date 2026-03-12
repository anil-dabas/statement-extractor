from .base_parser import BaseParser
from .airwallex_parser import AirwallexParser
from .bea_parser import BEAParser
from .dbs_parser import DBSParser
from .hangseng_parser import HangSengParser
from .hsbc_parser import HSBCParser

PARSERS = {
    "airwallex": AirwallexParser,
    "bea": BEAParser,
    "dbs": DBSParser,
    "hangseng": HangSengParser,
    "hsbc": HSBCParser,
}


def get_parser(bank_type: str) -> BaseParser:
    """Get the appropriate parser for a bank type."""
    parser_class = PARSERS.get(bank_type)
    if parser_class is None:
        raise ValueError(f"No parser available for bank type: {bank_type}")
    return parser_class()


__all__ = [
    "BaseParser",
    "AirwallexParser",
    "BEAParser",
    "DBSParser",
    "HangSengParser",
    "HSBCParser",
    "PARSERS",
    "get_parser",
]
