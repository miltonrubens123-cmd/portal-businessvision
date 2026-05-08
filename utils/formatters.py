import re


def formatar_cnpj(cnpj):
    cnpj = re.sub(r"\D", "", cnpj or "")
    if len(cnpj) == 14:
        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    return cnpj


def formatar_cpf(cpf):
    cpf = re.sub(r"\D", "", cpf or "")
    if len(cpf) == 11:
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    return cpf


def validar_cnpj(cnpj):
    return len(re.sub(r"\D", "", cnpj or "")) == 14


def validar_cpf(cpf):
    return len(re.sub(r"\D", "", cpf or "")) == 11
