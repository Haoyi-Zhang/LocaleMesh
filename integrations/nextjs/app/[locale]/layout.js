export default async function LocaleLayout({children,params}) {
  const {locale}=await params;
  return <html lang={locale}><body>{children}</body></html>;
}
