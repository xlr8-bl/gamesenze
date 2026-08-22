import PageHead from "@/components/PageHead";
import AuthForm from "@/components/AuthForm";

export default function SignIn() {
  return (
    <>
      <PageHead eyebrow="Account" title="Sign in" lede="Back to the board." />
      <div className="shell shell-tight" style={{ paddingTop: "var(--s-6)" }}>
        <AuthForm mode="signin" />
      </div>
    </>
  );
}
