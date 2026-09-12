import Form from "react-bootstrap/Form";

export default function AgentTextareas({
  botPersonality,
  usePersonality,
  onChange,
  onBlur,
}: {
  botPersonality: string;
  usePersonality: boolean;
  onChange: (key: string, value: string) => void;
  onBlur: () => void;
}) {
  return (
    <>
      {usePersonality && (
        <Form.Group className="mb-2">
          <Form.Label className="small">UwU Personality</Form.Label>
          <Form.Control
            as="textarea"
            rows={3}
            size="sm"
            value={botPersonality}
            onChange={(e) => onChange("botPersonality", e.target.value)}
            onBlur={onBlur}
            className="bg-dark text-light border-secondary"
          />
        </Form.Group>
      )}
    </>
  );
}
