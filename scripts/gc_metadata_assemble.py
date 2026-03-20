from dglink import NodeSet, EdgeSet, write_graph
from dglink.portals.nci.gc import nciGeneralCommonsClient
from dglink.portals.nci.gc.constants import NODE_ATTRIBUTES, EDGE_ATTRIBUTES

client = nciGeneralCommonsClient(gen3_credential_file='nci_general_commons_credentials')

lazzy_get = lambda d, x: f"{d.get(x, f'{x}_missing')}"

if __name__ == "__main__":
    
    node_set = NodeSet(attributes=NODE_ATTRIBUTES)
    edge_set = EdgeSet(attributes=EDGE_ATTRIBUTES)

    ## add programs and studies ## 
    program_details = client.get_program_details()
    for program in program_details:
        program_id = program.get("program")
        if not program_id:
            continue
        node_set.update_nodes(
            {
                "curie:ID": program_id,
                ":LABEL": "Program",
                "name": lazzy_get(program, "program_name"),
                "program_description": lazzy_get(program, "program_short_description"),
                "num_participants": lazzy_get(program, "num_participants"),
                "num_files": lazzy_get(program, "num_files"),
                "num_samples": lazzy_get(program, "num_samples"),
                "num_disease_sites": lazzy_get(program, "num_disease_sites"),
                "program_url": lazzy_get(program, "program_url"),
                "source:string[]": "structural_information",
            }
        )
        for study in program.get("studies", []):
            accession = study.get("accession")
            if not accession:
                continue
            node_set.update_nodes(
                {
                    "curie:ID": accession,
                    ":LABEL": "Study",
                    "name": lazzy_get(study, "study_name"),
                    "study_access": lazzy_get(study, "study_access"),
                    "study_version": lazzy_get(study, "study_version"),
                    "study_data_types": lazzy_get(study, "study_data_types"),
                    "short_description": lazzy_get(study, "short_description"),
                    "num_participants": lazzy_get(study, "num_participants"),
                    "num_samples": lazzy_get(study, "num_samples"),
                    "num_files": lazzy_get(study, "num_files"),
                    "source:string[]": "structural_information",
                }
            )
            edge_set.update_edges(
                {
                    ":START_ID": program_id,
                    ":END_ID": accession,
                    ":TYPE": "Has_Study",
                    "source:string[]": "structural_information",
                }
            )

        for participant_group in program.get("study_participants", []):
            group = participant_group.get("group")
            subjects = lazzy_get(participant_group, "subjects")
            if not group:
                continue

            node_set.update_nodes(
                {
                    "curie:ID": group,
                    ":LABEL": "StudyParticipantGroup",
                    "name": group,
                    "subject_count": subjects,
                    "source:string[]": "metadata",
                }
            )

            edge_set.update_edges(
                {
                    ":START_ID": program_id,
                    ":END_ID": group,
                    ":TYPE": "Has_Participant_Group",
                    "source:string[]": "metadata",
                }
            )

    ## add publications ##
    publications = client.get_publications()
    for publication in publications:
        doi = lazzy_get(publication, "DOI_or_Pub_ID")
        if not doi:
            continue

        node_set.update_nodes(
            {
                "curie:ID": doi,
                ":LABEL": "Publication",
                "name": lazzy_get(publication, "Publication_Title"),
                "publication_type": lazzy_get(publication, "Publication_Type"),
                "publication_status": lazzy_get(publication, "Publication_Status"),
                "doi": doi,
                "source:string[]": "metadata",
            }
        )

        for phs in publication.get("phs_accessions", [lazzy_get(publication, "phs_accession")]):
            edge_set.update_edges(
                {
                    ":START_ID": phs,
                    ":END_ID": doi,
                    ":TYPE": "Published",
                    "source:string[]": "metadata",
                }
            )

    ## add investigators ## 
    investigators = client.get_investigators()
    for investigator in investigators:
        inv_id = investigator.get("investigator_id")
        if not inv_id:
            continue

        # build a display name — fall back to primary_investigator_name if first/last absent
        first = investigator.get("first_name", "")
        last = investigator.get("last_name", "")
        display_name = (
            f"{first} {last}".strip()
            or lazzy_get(investigator, "primary_investigator_name")
        )

        node_set.update_nodes(
            {
                "curie:ID": inv_id,
                ":LABEL": "Investigator",
                "name": display_name,
                "email": lazzy_get(investigator, "email"),
                "role_or_affiliation": lazzy_get(investigator, "role_or_affiliation"),
                "title": lazzy_get(investigator, "title"),
                "source:string[]": "metadata",
            }
        )


        for phs in investigator.get("phs_accessions", [lazzy_get(investigator, "phs_accession")]):
            edge_set.update_edges(
                {
                    ":START_ID": inv_id,
                    ":END_ID": phs,
                    ":TYPE": "Leads_Study",
                    "role": lazzy_get(investigator, "role_or_affiliation"),
                    "source:string[]": "metadata",
                }
            )

    ## add diagnosis ##
    diagnoses = client.get_diagnoses(only_open=True)
    for diagnosis in diagnoses:
        diag_id = diagnosis.get("diagnosis_id")
        if not diag_id:
            continue

        node_set.update_nodes(
            {
                "curie:ID": diag_id,
                ":LABEL": "Diagnosis",
                "name": lazzy_get(diagnosis, "primary_diagnosis"),
                "disease_type": lazzy_get(diagnosis, "disease_type"),
                "primary_site": lazzy_get(diagnosis, "primary_site"),
                "tissue_or_organ_of_origin": lazzy_get(diagnosis, "tissue_or_organ_of_origin"),
                "site_of_resection_or_biopsy": lazzy_get(diagnosis, "site_of_resection_or_biopsy"),
                "tumor_grade": lazzy_get(diagnosis, "tumor_grade"),
                "tumor_stage_clinical_m": lazzy_get(diagnosis, "tumor_stage_clinical_m"),
                "tumor_stage_clinical_n": lazzy_get(diagnosis, "tumor_stage_clinical_n"),
                "tumor_stage_clinical_t": lazzy_get(diagnosis, "tumor_stage_clinical_t"),
                "morphology": lazzy_get(diagnosis, "morphology"),
                "vital_status": lazzy_get(diagnosis, "vital_status"),
                "age_at_diagnosis": lazzy_get(diagnosis, "age_at_diagnosis"),
                "incidence_type": lazzy_get(diagnosis, "incidence_type"),
                "progression_or_recurrence": lazzy_get(diagnosis, "progression_or_recurrence"),
                "last_known_disease_status": lazzy_get(diagnosis, "last_known_disease_status"),
                "crdc_id": lazzy_get(diagnosis, "crdc_id"),
                "source:string[]": "clinical",
            }
        )
        phs = diagnosis.get("phs_accession")
        if phs:
            edge_set.update_edges(
                {
                    ":START_ID": phs,
                    ":END_ID": diag_id,
                    ":TYPE": "Study_Has_Diagnosis",
                    "source:string[]": "clinical",
                }
            )
    ## write results ##
    write_graph(node_set=node_set, edge_set=edge_set, resource_path="nci_gc_graph")