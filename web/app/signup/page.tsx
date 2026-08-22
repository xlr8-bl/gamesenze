import PageHead from "@/components/PageHead";
import AuthForm from "@/components/AuthForm";

export default function SignUp() {
  return (
    <>
      <PageHead
        eyebrow="Account"
        title="Create an account"
        lede="The record is public whether you sign up or not. An account is what gets you the board."
      />
      <div className="shell shell-tight" style={{ paddingTop: "var(--s-6)" }}>
        <AuthForm mode="signup" />
      </div>
    </>
  );
}
