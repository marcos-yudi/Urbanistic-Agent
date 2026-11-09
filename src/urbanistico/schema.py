"""Schema Pydantic dos parâmetros urbanísticos (Lei nº 13.905/2024, Anexo II).

Dois níveis:
- Extração (o que o LLM devolve): ``ExtracaoZona`` → ``LinhaExtraida`` → ``ValorExtraido``,
  em formato largo (um campo por parâmetro), para o LLM não pular parâmetros.
- Canônico (gabarito, BigQuery, avaliação): ``RegistroParametro``, em formato longo,
  uma linha por ``zona + linha + parametro``.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Parametro(StrEnum):
    TAXA_OCUPACAO_TERREO = "taxa_ocupacao_terreo"
    TAXA_OCUPACAO_DEMAIS = "taxa_ocupacao_demais"
    CA_BASICO = "ca_basico"
    CA_MAXIMO = "ca_maximo"
    GABARITO = "gabarito"
    PERMEABILIDADE_MIN = "permeabilidade_min"
    RECUO_FRONTAL = "recuo_frontal"


class Linha(StrEnum):
    """Linha do quadro do Anexo II; cada uma vale para todos os usos listados nela."""

    RES_RUB = "RES-RUB"
    RES_RMV = "RES-RMV"
    NAO_RES = "NAO-RES"


class TipoValor(StrEnum):
    NUMERO = "numero"
    NAO_DEFINIDO = "nao_definido"  # o quadro mostra "–": não é zero nem "sem limite"
    DE_ORIGEM = "de_origem"  # ZEICs (futuro): herda o parâmetro da zona de origem


# A unidade é função do parâmetro, por isso não é pedida ao LLM.
UNIDADES: dict[Parametro, str | None] = {
    Parametro.TAXA_OCUPACAO_TERREO: "%",
    Parametro.TAXA_OCUPACAO_DEMAIS: "%",
    Parametro.CA_BASICO: None,
    Parametro.CA_MAXIMO: None,
    Parametro.GABARITO: "pav",
    Parametro.PERMEABILIDADE_MIN: "%",
    Parametro.RECUO_FRONTAL: "m",
}

_PERCENTUAIS = {
    Parametro.TAXA_OCUPACAO_TERREO,
    Parametro.TAXA_OCUPACAO_DEMAIS,
    Parametro.PERMEABILIDADE_MIN,
}


def _vazio_para_none(valor):
    """O CSV representa ausência com string vazia; no modelo ela vira None."""
    if isinstance(valor, str) and valor.strip() == "":
        return None
    return valor


def _checar_valor_x_tipo(valor: float | None, tipo_valor: TipoValor) -> None:
    """Regra central contra alucinação: só há número quando o tipo é ``numero``."""
    if tipo_valor == TipoValor.NUMERO and valor is None:
        raise ValueError("tipo_valor 'numero' exige valor preenchido")
    if tipo_valor != TipoValor.NUMERO and valor is not None:
        raise ValueError(f"tipo_valor '{tipo_valor.value}' exige valor nulo, recebeu {valor}")


def _checar_faixa(parametro: Parametro, valor: float | None) -> None:
    """Faixas plausíveis por parâmetro. Ficam em validador (e não em Field(ge=...))
    para manter simples o JSON Schema enviado ao Gemini."""
    if valor is None:
        return
    if parametro in _PERCENTUAIS and not 0 <= valor <= 100:
        raise ValueError(f"{parametro.value} deve estar entre 0 e 100, recebeu {valor}")
    if parametro in (Parametro.CA_BASICO, Parametro.CA_MAXIMO) and valor < 0:
        raise ValueError(f"{parametro.value} não pode ser negativo, recebeu {valor}")
    if parametro == Parametro.RECUO_FRONTAL and valor < 0:
        raise ValueError(f"recuo_frontal não pode ser negativo, recebeu {valor}")
    if parametro == Parametro.GABARITO and (valor < 1 or valor != int(valor)):
        raise ValueError(f"gabarito deve ser inteiro >= 1 (pavimentos), recebeu {valor}")


# ---------------------------------------------------------------------------
# Modelo canônico (formato longo)
# ---------------------------------------------------------------------------


class RegistroParametro(BaseModel):
    """Uma linha do gabarito.csv / da tabela no BigQuery."""

    model_config = ConfigDict(frozen=True)

    zona: str
    linha: Linha
    parametro: Parametro
    valor: float | None = None
    unidade: str | None = None
    tipo_valor: TipoValor
    nota: str | None = None
    fonte: str
    pagina: int = Field(ge=1)

    @field_validator("valor", "unidade", "nota", mode="before")
    @classmethod
    def _limpar_vazio(cls, v):
        return _vazio_para_none(v)

    @model_validator(mode="after")
    def _validar(self):
        _checar_valor_x_tipo(self.valor, self.tipo_valor)
        _checar_faixa(self.parametro, self.valor)
        esperada = UNIDADES[self.parametro]
        if self.unidade != esperada:
            raise ValueError(
                f"unidade de {self.parametro.value} deve ser {esperada!r}, recebeu {self.unidade!r}"
            )
        return self

    @property
    def chave(self) -> tuple[str, Linha, Parametro]:
        return (self.zona, self.linha, self.parametro)


# ---------------------------------------------------------------------------
# Modelos da extração (saída do LLM, formato largo)
# ---------------------------------------------------------------------------


class ValorExtraido(BaseModel):
    """Valor de uma célula do quadro, com a nota de rodapé que o condiciona."""

    valor: float | None = Field(
        default=None, description="Número da célula; nulo se o quadro mostra '–'."
    )
    tipo_valor: TipoValor = Field(
        description="'numero' se há número; 'nao_definido' se o quadro mostra '–'."
    )
    nota: str | None = Field(
        default=None, description="Texto da nota de rodapé que condiciona o valor, se houver."
    )

    @model_validator(mode="after")
    def _validar(self):
        _checar_valor_x_tipo(self.valor, self.tipo_valor)
        return self


class LinhaExtraida(BaseModel):
    """Uma linha do quadro: todos os 7 parâmetros são obrigatórios."""

    linha: Linha
    taxa_ocupacao_terreo: ValorExtraido
    taxa_ocupacao_demais: ValorExtraido
    ca_basico: ValorExtraido
    ca_maximo: ValorExtraido
    gabarito: ValorExtraido
    permeabilidade_min: ValorExtraido
    recuo_frontal: ValorExtraido

    @model_validator(mode="after")
    def _validar_faixas(self):
        for parametro in Parametro:
            _checar_faixa(parametro, getattr(self, parametro.value).valor)
        return self


class ExtracaoZona(BaseModel):
    """Resultado da extração de um quadro (uma zona, uma página)."""

    zona: str
    pagina: int = Field(ge=1)
    fonte: str = "Anexo II"
    linhas: list[LinhaExtraida]

    @field_validator("linhas")
    @classmethod
    def _sem_linha_repetida(cls, linhas: list[LinhaExtraida]):
        nomes = [item.linha for item in linhas]
        repetidas = {n.value for n in nomes if nomes.count(n) > 1}
        if repetidas:
            raise ValueError(f"linhas repetidas no quadro: {sorted(repetidas)}")
        return linhas

    def para_formato_longo(self) -> list[RegistroParametro]:
        """Converte para o formato do gabarito (uma linha por zona + linha + parametro)."""
        registros = []
        for item in self.linhas:
            for parametro in Parametro:
                extraido: ValorExtraido = getattr(item, parametro.value)
                registros.append(
                    RegistroParametro(
                        zona=self.zona,
                        linha=item.linha,
                        parametro=parametro,
                        valor=extraido.valor,
                        unidade=UNIDADES[parametro],
                        tipo_valor=extraido.tipo_valor,
                        nota=extraido.nota,
                        fonte=self.fonte,
                        pagina=self.pagina,
                    )
                )
        return registros
