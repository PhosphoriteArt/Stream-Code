import logging
import sys
from better_profanity import profanity

def create_logger(service_name: str, level: int = logging.DEBUG):
    logger = logging.getLogger(service_name)
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

def create_filter():
    return profanity.load_censor_words(
        whitelist_words=[
            "fuck",
            "shit",
            "damn",
            "goddamn",
            "ass",
            "shitty",
            "fucking",
            "fucked",
            "hell",
            "crap",
            "asshole",
            "dick",
            "drunk",
            "dumb",
            "dumbass",
            "fat",
            "gay",
            "gays",
            "god",
            "homo",
            "lesbian",
            "lesbians",
            "lmao",
            "lust",
            "loin",
            "loins",
            "masochist",
            "menstruate",
            "naked",
            "nude",
            "nudes",
            "omg",
            "pee",
            "piss",
            "pot",
            "puss",
            "screw",
            "sex",
            "sexual",
            "smut",
            "stoned",
            "suck",
            "sucks",
            "tampon",
            "sucked",
            "thug",
            "thrust",
            "trashy",
            "ugly",
            "vomit",
            "weed",
            "weirdo",
            "weird",
            "womb",
            "yaoi",
            "yuri",
            "yury",
        ]
    )