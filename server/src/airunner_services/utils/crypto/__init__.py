"""Service-owned encryption helpers."""
from __future__ import annotations

from airunner_services.utils.crypto.data_encryption import (
    DataEncryptionError,
)
from airunner_services.utils.crypto.data_encryption import Keyring
from airunner_services.utils.crypto.data_encryption import decrypt_bytes
from airunner_services.utils.crypto.data_encryption import encrypt_bytes
from airunner_services.utils.crypto.data_encryption import (
    generate_fernet_key,
)
from airunner_services.utils.crypto.data_encryption import get_keyring
from airunner_services.utils.crypto.dek_cache import (
    cache_evict,
    cache_get,
    cache_set,
    cache_touch,
    get_user_dek,
    reset_user_dek,
    set_user_dek,
)
from airunner_services.utils.crypto.user_encrypted_type import (
    UserEncryptedText,
)
from airunner_services.utils.crypto.user_envelope import (
    EnvelopeError,
    decode_salt,
    derive_kek,
    encode_salt,
    generate_dek,
    generate_kdf_salt,
    unwrap_dek,
    wrap_dek,
)
from airunner_services.utils.crypto.fhe_helpers import (
    encrypt_embedding,
    generate_fhe_context,
    l2_normalize,
)
from airunner_services.utils.crypto.fhe_key_wrap import (
    unwrap_secret_context,
    wrap_secret_context,
)
from airunner_services.utils.crypto.fhe_cache import (
    fhe_cache_evict,
    fhe_cache_get,
    fhe_cache_set,
    fhe_cache_touch,
    get_fhe_context,
    set_fhe_context,
)
from airunner_services.utils.crypto.fhe_search import (
    FHE_CANDIDATE_CAP,
    fhe_similarity_rank,
)
from airunner_services.utils.crypto.fhe_account_context import (
    get_or_create_public_context,
)

__all__ = [
    "DataEncryptionError",
    "EnvelopeError",
    "FHE_CANDIDATE_CAP",
    "Keyring",
    "UserEncryptedText",
    "cache_evict",
    "cache_get",
    "cache_set",
    "cache_touch",
    "decode_salt",
    "decrypt_bytes",
    "derive_kek",
    "encode_salt",
    "encrypt_bytes",
    "encrypt_embedding",
    "fhe_cache_evict",
    "fhe_cache_get",
    "fhe_cache_set",
    "fhe_cache_touch",
    "fhe_similarity_rank",
    "generate_dek",
    "generate_fernet_key",
    "generate_fhe_context",
    "generate_kdf_salt",
    "get_fhe_context",
    "get_keyring",
    "get_or_create_public_context",
    "get_user_dek",
    "l2_normalize",
    "reset_user_dek",
    "set_fhe_context",
    "set_user_dek",
    "unwrap_dek",
    "unwrap_secret_context",
    "wrap_dek",
    "wrap_secret_context",
]
