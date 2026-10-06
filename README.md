## KSEB Data

KSEB data integration and solar grid availability

#### License

gpl-3.0

## Native annexure PDFs

KSEB Grid Check has separate editable Annexure I, II, III, and Office
Acknowledgement sections. Existing consumer/load/capacity fields are reused.
Generate → Annexure 1/2/3 saves pending edits and automatically renders the matching
native Frappe print format, attaching a private PDF. Stored dates, installation
type (Rooftop by default), and other choices are preserved on subsequent prints.
The existing `generate_annexure1/2/3` API names and file response keys are retained.
No new generation action reads a fillable PDF template.

The app bundles Manjari Regular and Bold from the official SMC distribution,
with its SIL Open Font License in `wahni_kseb/public/fonts/manjari/OFL.txt`.
The fonts are embedded through print CSS, so rendering requires no external font
service. The templates preserve the Malayalam text, table/receipt structure,
and signature spaces of the original annexures.

Deploy this update together with the corresponding `wahni_solar` native-document
update. Run `bench --site YOUR_SITE migrate`, build both apps' assets, and restart
workers. The one-time annexure defaults patch affects newly introduced static
fields only; it never runs during generation. Existing attachments are preserved.

Run `python -m unittest wahni_kseb.annexure.test_printing` inside a bench environment
for native rendering dispatch, saved-date, and font/escaping tests.
