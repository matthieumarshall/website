from website.models import AdministrationDocument, AdministrationSection


ADMINISTRATION_DOCUMENT_SECTIONS: list[AdministrationSection] = [
    AdministrationSection(
        id="notices",
        title="Notices",
        description="League notices and official communications.",
        documents=[
            AdministrationDocument(
                name="Notice to Clubs (PDF)",
                href="/uploads/administration/notices/notice-to-clubs.pdf",
                file_type="PDF",
            ),
            AdministrationDocument(
                name="Notice Archive (ZIP)",
                href="/uploads/administration/notices/notice-archive.zip",
                file_type="ZIP",
            ),
        ],
    ),
    AdministrationSection(
        id="agendas",
        title="Agendas",
        description="Meeting agendas published ahead of committee sessions.",
        documents=[
            AdministrationDocument(
                name="Committee Agenda (PDF)",
                href="/uploads/administration/agendas/committee-agenda.pdf",
                file_type="PDF",
            ),
            AdministrationDocument(
                name="Agenda Pack (ZIP)",
                href="/uploads/administration/agendas/agenda-pack.zip",
                file_type="ZIP",
            ),
        ],
    ),
    AdministrationSection(
        id="meeting-notes",
        title="Meeting notes",
        description="Approved notes and supporting meeting documents.",
        documents=[
            AdministrationDocument(
                name="Meeting Notes (PDF)",
                href="/uploads/administration/meeting-notes/meeting-notes.pdf",
                file_type="PDF",
            ),
            AdministrationDocument(
                name="Meeting Notes Attachments (ZIP)",
                href="/uploads/administration/meeting-notes/meeting-notes-pack.zip",
                file_type="ZIP",
            ),
        ],
    ),
    AdministrationSection(
        id="accounts",
        title="Accounts",
        description="Accounts packs and published financial summaries.",
        documents=[
            AdministrationDocument(
                name="Annual Accounts (PDF)",
                href="/uploads/administration/accounts/annual-accounts.pdf",
                file_type="PDF",
            ),
            AdministrationDocument(
                name="Accounts Supporting Files (ZIP)",
                href="/uploads/administration/accounts/accounts-supporting-files.zip",
                file_type="ZIP",
            ),
        ],
    ),
]
