# factures/pdf.py
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    HRFlowable, Image
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from io import BytesIO
import os
from xml.sax.saxutils import escape

MOIS_FR = {
    1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
    5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
    9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
}

def date_fr(d):
    return f"{d.day:02d} {MOIS_FR[d.month]} {d.year}"

BLEU       = colors.HexColor('#1e3a5f')
BLEU_CLAIR = colors.HexColor('#2d6a9f')
GRIS_CLAIR = colors.HexColor('#f2f2f2')
GRIS       = colors.HexColor('#6c757d')
BLANC      = colors.white
NOIR       = colors.black
VERT       = colors.HexColor('#2d6a9f')
ROUGE      = colors.HexColor('#dc3545')
ORANGE     = colors.HexColor('#fd7e14')


def montant_en_lettres(montant, devise='FCFA'):
    units = ['', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept',
             'huit', 'neuf', 'dix', 'onze', 'douze', 'treize', 'quatorze',
             'quinze', 'seize', 'dix-sept', 'dix-huit', 'dix-neuf']
    tens  = ['', 'dix', 'vingt', 'trente', 'quarante', 'cinquante',
             'soixante', 'soixante', 'quatre-vingt', 'quatre-vingt']

    def moins_de_mille(n):
        if n == 0: return ''
        elif n < 20: return units[n]
        elif n < 100:
            t, u = divmod(n, 10)
            if t == 7: return 'soixante-' + units[10 + u]
            elif t == 9: return 'quatre-vingt-' + units[u] if u else 'quatre-vingt'
            elif t == 8: return 'quatre-vingt-' + units[u] if u else 'quatre-vingts'
            else: return tens[t] + ('-' + units[u] if u else '')
        else:
            c, reste = divmod(n, 100)
            cent = ('cent' if c == 1 else units[c] + ' cent')
            cent += 's' if reste == 0 and c > 1 else ''
            return (cent + ' ' + moins_de_mille(reste)).strip()

    try:
        n = int(montant)
        if n == 0: return 'Zéro'
        resultat = ''
        if n >= 1000000:
            m, reste = divmod(n, 1000000)
            resultat += moins_de_mille(m) + ' million' + ('s' if m > 1 else '')
            n = reste
        if n >= 1000:
            m, reste = divmod(n, 1000)
            resultat += (' mille' if m == 1 else ' ' + moins_de_mille(m) + ' mille')
            n = reste
        if n > 0: resultat += ' ' + moins_de_mille(n)
        return resultat.strip().capitalize()
    except Exception:
        return str(montant)


def texte_pdf(texte):
    """Texte libre affiché en entier dans le PDF (caractères spéciaux et retours à la ligne)."""
    return escape(texte or '').replace('\n', '<br/>')


def _get_profil(utilisateur):
    try:
        from users.models import ProfilUtilisateur
        return ProfilUtilisateur.objects.get(user=utilisateur)
    except Exception:
        return None


def _logo_image(path, largeur=3.5*cm, hauteur=2*cm):
    try:
        if path and os.path.exists(path):
            return Image(path, width=largeur, height=hauteur, kind='proportional')
    except Exception:
        pass
    return None


def generer_pdf_facture(facture):
    from clients.portail import url_portail_public
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=1.8*cm, leftMargin=1.8*cm,
        topMargin=1.5*cm,   bottomMargin=1.5*cm
    )

    elements = []
    s_normal = ParagraphStyle('s_normal', fontSize=9,  fontName='Helvetica',      leading=13)
    s_bold   = ParagraphStyle('s_bold',   fontSize=9,  fontName='Helvetica-Bold', leading=13)
    s_small  = ParagraphStyle('s_small',  fontSize=8,  fontName='Helvetica',      textColor=GRIS, leading=11)
    s_right  = ParagraphStyle('s_right',  fontSize=9,  fontName='Helvetica',      alignment=TA_RIGHT, leading=13)
    s_center = ParagraphStyle('s_center', fontSize=9,  fontName='Helvetica',      alignment=TA_CENTER)

    utilisateur = facture.utilisateur
    client      = facture.client
    profil      = _get_profil(utilisateur)

    # ── Nom émetteur
    nom_emetteur = (profil.nom_entreprise if profil and profil.nom_entreprise
                    else f"{utilisateur.first_name} {utilisateur.last_name}".strip()
                    or utilisateur.username)
    nom_client = f"{client.nom} {client.prenom}".strip()

    # ── ✅ Devise : priorité à la devise choisie par l'utilisateur
    if facture.devise_choisie:
        devise = facture.devise_choisie
    elif hasattr(client, 'pays_obj') and client.pays_obj:
        devise = client.pays_obj.devise_symbole or 'FCFA'
    else:
        devise = 'FCFA'

    # ── Infos taxe
    pays_label = facture.pays or (client.pays_obj.nom if client.pays_obj else '')
    
    taxes_details = facture.get_taxes_details()
    total_ht = facture.calculer_total_ht()
    total_tva = facture.calculer_tva()
    total_ttc = facture.calculer_total_ttc()

    # ── Adresse client
    adresse_client_lines = []
    if client.adresse: adresse_client_lines.append(client.adresse)
    if client.ville:
        ville_str = client.ville
        if client.code_postal: ville_str += f" {client.code_postal}"
        if client.province:    ville_str += f" ({client.province})"
        adresse_client_lines.append(ville_str)
    if client.pays_obj: adresse_client_lines.append(client.pays_obj.nom)

    # ── Statut avec couleurs pour le cachet
    statut_map = {
        'en_attente': ('EN ATTENTE D\'APPROBATION', ORANGE),
        'approuvee': ('APPROUVÉE', VERT),
        'rejetee': ('REJETÉE', ROUGE),
        'non_payee': ('NON PAYÉE', ROUGE),
        'payee': ('PAYÉE', VERT),
        'annulee': ('ANNULÉE', GRIS),
    }
    statut_texte, statut_couleur = statut_map.get(facture.statut, ('', GRIS))

    # ══════════════════════════════════════════
    # LOGOS
    # ══════════════════════════════════════════
    logo_emetteur = None
    if profil and profil.logo:
        logo_emetteur = _logo_image(profil.logo.path, largeur=4*cm, hauteur=2.2*cm)

    logo_client = None
    if hasattr(client, 'logo') and client.logo:
        logo_client = _logo_image(client.logo.path, largeur=4*cm, hauteur=2.2*cm)

    # ── Colonne émetteur
    col_emetteur = []
    if logo_emetteur:
        col_emetteur.append(logo_emetteur)
        col_emetteur.append(Spacer(1, 0.25*cm))
    col_emetteur.append(Paragraph(f"<b>{nom_emetteur}</b>", s_bold))
    if profil:
        if profil.telephone:
            col_emetteur.append(Paragraph(f"Tél : {profil.telephone}", s_normal))
        email_e = profil.email_entreprise or utilisateur.email or ''
        if email_e:
            col_emetteur.append(Paragraph(email_e, s_normal))
        if profil.site_web:
            col_emetteur.append(Paragraph(profil.site_web, s_small))
        if profil.adresse:
            col_emetteur.append(Paragraph(profil.adresse, s_small))
        if profil.ville:
            ville = f"{profil.code_postal} {profil.ville}".strip() if profil.code_postal else profil.ville
            col_emetteur.append(Paragraph(ville, s_small))
        if profil.pays:
            col_emetteur.append(Paragraph(profil.pays, s_small))
    else:
        col_emetteur.append(Paragraph(utilisateur.email or '', s_normal))

    # ── Colonne titre FACTURE
    col_titre = [
        Paragraph('FACTURE', ParagraphStyle(
            'titre', fontSize=24, fontName='Helvetica-Bold',
            textColor=BLEU, alignment=TA_CENTER
        )),
        Spacer(1, 0.5*cm),
        Paragraph(f"N° : <b>{facture.numero}</b>", ParagraphStyle(
            'num', fontSize=10, fontName='Helvetica', alignment=TA_CENTER
        )),
        Spacer(1, 0.2*cm),
        Paragraph(f"Date : {date_fr(facture.date_creation)}", ParagraphStyle(
            'date', fontSize=9, fontName='Helvetica',
            alignment=TA_CENTER, textColor=GRIS
        )),
        Spacer(1, 0.2*cm),
        Paragraph(f"Échéance : {date_fr(facture.date_echeance)}", ParagraphStyle(
            'echeance', fontSize=9, fontName='Helvetica-Bold',
            alignment=TA_CENTER, textColor=BLEU
        )),
    ]

    # ── Colonne client
    col_client = []
    if logo_client:
        col_client.append(logo_client)
        col_client.append(Spacer(1, 0.25*cm))
    col_client.append(Paragraph("Facturé à :", s_small))
    col_client.append(Paragraph(f"<b>{nom_client}</b>", s_bold))
    if client.entreprise:
        col_client.append(Paragraph(client.entreprise, s_normal))
    if client.email:
        col_client.append(Paragraph(client.email, s_normal))
    if hasattr(client, 'telephone_complet') and client.telephone_complet:
        col_client.append(Paragraph(f"Tél : {client.telephone_complet}", s_normal))
    for line in adresse_client_lines:
        col_client.append(Paragraph(line, s_small))
    col_client.append(Paragraph(f"Identifiant client : <b>{client.identifiant_portail}</b>", s_small))
    url_portail = url_portail_public()
    if url_portail:
        col_client.append(Paragraph(f"Espace client : {url_portail}", s_small))

    # ── Table en-tête 3 colonnes
    header_data = [[col_emetteur, col_titre, col_client]]
    header_table = Table(header_data, colWidths=[6*cm, 6*cm, 6*cm])
    header_table.setStyle(TableStyle([
        ('VALIGN',  (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.3*cm))
    elements.append(HRFlowable(width="100%", thickness=2, color=BLEU))
    elements.append(Spacer(1, 0.3*cm))

    # ══════════════════════════════════════════
    # INFOS FACTURE
    # ══════════════════════════════════════════
    pays_str = f" — {pays_label}" if pays_label else ""
    infos_data = [[
        Paragraph(f"<b>Facture N° :</b> {facture.numero}", s_normal),
        Paragraph(f"<b>Date :</b> {date_fr(facture.date_creation)}", s_normal),
        Paragraph(
            f"<b>Échéance :</b> {date_fr(facture.date_echeance)}"
            f"{pays_str}",
            s_normal
        ),
    ]]
    infos_table = Table(infos_data, colWidths=[6*cm, 6*cm, 6*cm])
    infos_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), GRIS_CLAIR),
        ('PADDING',    (0, 0), (-1, -1), 8),
        ('VALIGN',     (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(infos_table)

    # ══════════════════════════════════════════
    # BANDEAU TAXES ET DEVISE - CHAQUE TAXE SUR SA PROPRE LIGNE
    # ══════════════════════════════════════════
    elements.append(Spacer(1, 0.2*cm))
    
    # ✅ CORRECTION : Filtrer les taxes avec taux > 0 pour l'affichage
    taxes_a_afficher = [t for t in taxes_details if t.get('taux', 0) > 0]
    
    # Construction du texte des taxes avec chaque taxe sur une ligne
    if taxes_a_afficher and len(taxes_a_afficher) > 0:
        # Créer une ligne par taxe avec son pourcentage (uniquement si taux > 0)
        taxe_lines = []
        for taxe in taxes_a_afficher:
            taxe_lines.append(f"• {taxe['code']} : {taxe['taux']}%")
        
        # Joindre avec des sauts de ligne HTML
        taxe_text = "<br/>".join(taxe_lines)
        taxe_paragraph = Paragraph(
            f"<b>Taxes appliquées :</b><br/>{taxe_text}",
            ParagraphStyle('taxes', fontSize=9, fontName='Helvetica', leading=14)
        )
    else:
        # ✅ Afficher "TVA 0%" quand aucune taxe avec taux > 0
        taxe_paragraph = Paragraph(
            f"<b>Taxes :</b> TVA 0%",
            s_normal
        )
    
    taxe_data = [[
        Paragraph(f"<b>Pays :</b> {pays_label or 'Non spécifié'}", s_normal),
        taxe_paragraph,
        Paragraph(f"<b>Devise :</b> {devise}", s_bold),
    ]]
    taxe_table = Table(taxe_data, colWidths=[6*cm, 6*cm, 6*cm])
    taxe_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e8f0fe')),
        ('PADDING',    (0, 0), (-1, -1), 8),
        ('VALIGN',     (0, 0), (-1, -1), 'TOP'),
        ('LINEBEFORE', (0, 0), (0, -1), 3, BLEU_CLAIR),
    ]))
    elements.append(taxe_table)
    elements.append(Spacer(1, 0.4*cm))

    # ══════════════════════════════════════════
    # TABLEAU DES LIGNES - ✅ PLUS DE COLONNE TVA%
    # ══════════════════════════════════════════
    lignes = facture.lignes.all()

    def th(txt):
        return Paragraph(f'<b>{txt}</b>', ParagraphStyle(
            'th', fontSize=9, fontName='Helvetica-Bold',
            textColor=BLANC, alignment=TA_CENTER
        ))

    # ✅ En-tête sans TVA%
    entete = [th('Produit / Service'), th('Description'), th('Qté'),
              th(f'P.U. ({devise})'), th(f'HT ({devise})')]
    rows = [entete]

    for ligne in lignes:
        montant_ht = ligne.quantite * ligne.prix_unitaire
        rows.append([
            Paragraph(texte_pdf(ligne.produit.nom if getattr(ligne, 'produit_id', None) else ligne.description), s_normal),
            Paragraph(texte_pdf(ligne.description), s_small),
            Paragraph(str(ligne.quantite).rstrip('0').rstrip('.'), s_center),
            Paragraph(f"{ligne.prix_unitaire:,.2f}", s_right),
            Paragraph(f"{montant_ht:,.2f}", s_right),
        ])

    # ✅ Ajustement des largeurs de colonnes (suppression de la colonne TVA)
    col_widths = [4.5*cm, 4.5*cm, 1.5*cm, 2.5*cm, 3*cm]
    lignes_table = Table(rows, colWidths=col_widths)
    lignes_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), BLEU),
        ('TEXTCOLOR',     (0, 0), (-1, 0), BLANC),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, 0), 9),
        ('ALIGN',         (0, 0), (-1, 0), 'CENTER'),
        ('PADDING',       (0, 0), (-1, 0), 8),
        ('FONTNAME',      (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',      (0, 1), (-1, -1), 9),
        ('PADDING',       (0, 1), (-1, -1), 7),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [BLANC, GRIS_CLAIR]),
        ('GRID',          (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(lignes_table)
    elements.append(Spacer(1, 0.4*cm))

    # ══════════════════════════════════════════
    # TOTAUX
    # ══════════════════════════════════════════
    
    totaux_rows = []
    
    # Ligne HT
    totaux_rows.append([
        '', '', Paragraph('<b>Sous total HT :</b>', s_right),
        Paragraph(f"{total_ht:,.2f} {devise}", s_right)
    ])
    
    # ✅ Lignes pour chaque taxe individuelle (UNIQUEMENT si taux > 0)
    for taxe in taxes_details:
        if taxe.get('taux', 0) > 0:
            totaux_rows.append([
                '', '', Paragraph(f'<b>{taxe["code"]} ({taxe["taux"]}%) :</b>', s_right),
                Paragraph(f"{taxe['montant']:,.2f} {devise}", s_right)
            ])
    
    # ✅ Si aucune taxe avec taux > 0, afficher "TVA 0%"
    if not any(t.get('taux', 0) > 0 for t in taxes_details):
        totaux_rows.append([
            '', '', Paragraph('<b>TVA (0%) :</b>', s_right),
            Paragraph(f"0,00 {devise}", s_right)
        ])
    
    # Ligne TTC
    totaux_rows.append([
        '', '', Paragraph('<b>Total TTC :</b>', ParagraphStyle(
            'tot', fontSize=10, fontName='Helvetica-Bold',
            alignment=TA_RIGHT, textColor=BLEU)),
        Paragraph(f"<b>{total_ttc:,.2f} {devise}</b>", ParagraphStyle(
            'tot2', fontSize=10, fontName='Helvetica-Bold',
            alignment=TA_RIGHT, textColor=BLEU))
    ])
    
    totaux_table = Table(totaux_rows, colWidths=[3*cm, 5*cm, 5.5*cm, 4.5*cm])
    
    style_commands = [
        ('PADDING', (0, 0), (-1, -1), 5),
        ('LINEABOVE', (2, len(totaux_rows)-1), (3, len(totaux_rows)-1), 1, BLEU),
        ('BACKGROUND', (2, len(totaux_rows)-1), (3, len(totaux_rows)-1), GRIS_CLAIR),
    ]
    
    for i in range(1, len(totaux_rows) - 1):
        style_commands.append(('LINEABOVE', (2, i), (3, i), 0.5, colors.HexColor('#dddddd')))
    
    totaux_table.setStyle(TableStyle(style_commands))
    elements.append(totaux_table)

    # ══════════════════════════════════════════
    # MONTANT EN LETTRES
    # ══════════════════════════════════════════
    elements.append(Spacer(1, 0.3*cm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=GRIS))
    elements.append(Spacer(1, 0.2*cm))
    lettres = montant_en_lettres(total_ttc, devise)
    elements.append(Paragraph(
        f"Arrêtée la présente facture à la somme de "
        f"<b>{lettres} ({total_ttc:,.2f}) {devise}</b>.",
        ParagraphStyle('lettres', fontSize=9, fontName='Helvetica',
                       textColor=BLEU, leading=14)
    ))

    if facture.notes:
        elements.append(Spacer(1, 0.4*cm))
        elements.append(Paragraph(f"<b>Notes :</b> {facture.notes}", s_normal))

    # ══════════════════════════════════════════
    # CACHET D'APPROBATION
    # ══════════════════════════════════════════
    STATUTS_AVEC_CACHET = ['payee', 'annulee', 'approuvee']
    
    if facture.statut in STATUTS_AVEC_CACHET:
        elements.append(Spacer(1, 0.5*cm))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=GRIS))
        elements.append(Spacer(1, 0.3*cm))

        cachet_data = [
            ['', Paragraph(
                f"<b>{statut_texte}</b>",
                ParagraphStyle('cachet', fontSize=12, fontName='Helvetica-Bold',
                               textColor=statut_couleur, alignment=TA_RIGHT, leading=16)
            )],
        ]
        cachet_table = Table(cachet_data, colWidths=[12*cm, 6*cm])
        cachet_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(cachet_table)

    # ══════════════════════════════════════════
    # PIED DE PAGE
    # ══════════════════════════════════════════
    elements.append(Spacer(1, 0.5*cm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=GRIS))
    elements.append(Spacer(1, 0.2*cm))

    if profil and profil.mention_legale:
        elements.append(Paragraph(
            profil.mention_legale,
            ParagraphStyle('mention', fontSize=7, fontName='Helvetica',
                           textColor=GRIS, leading=10, alignment=TA_CENTER)
        ))
        elements.append(Spacer(1, 0.15*cm))

    elements.append(Paragraph(
        f"Document généré automatiquement — {facture.numero} — {date_fr(facture.date_creation)}",
        ParagraphStyle('footer', fontSize=7, fontName='Helvetica',
                       textColor=GRIS, alignment=TA_CENTER)
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer